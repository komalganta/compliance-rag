import os
import sys
import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv
from fastembed import TextEmbedding

load_dotenv()


def get_connection():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def embed_query(model: TextEmbedding, question: str) -> list[float]:
    """Embed a single question the same way chunks were embedded."""
    return list(model.embed([question]))[0].tolist()


def vector_search(cur, query_vector: list[float], top_k: int = 20) -> list[tuple]:
    """Find chunks closest in meaning to the query vector."""
    cur.execute(
        """
        SELECT id, entity_id, entity_type, entity_name, text,
               embedding <=> %s::vector AS distance
        FROM chunks
        ORDER BY distance
        LIMIT %s
        """,
        (query_vector, top_k),
    )
    return cur.fetchall()


def keyword_search(cur, question: str, top_k: int = 20) -> list[tuple]:
    """Find chunks using Postgres full-text search (keyword matching).
    Words are OR'd together so a chunk matching ANY significant word
    can surface, not just chunks matching every word."""
    or_query = " | ".join(question.split())
    cur.execute(
        """
        SELECT id, entity_id, entity_type, entity_name, text,
               ts_rank(tsv, to_tsquery('english', %s)) AS rank
        FROM chunks
        WHERE tsv @@ to_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT %s
        """,
        (or_query, or_query, top_k),
    )
    return cur.fetchall()


def reciprocal_rank_fusion(vector_results: list[tuple], keyword_results: list[tuple], k: int = 60, top_k: int = 5) -> list[tuple]:
    """Merge two ranked result lists into one, using Reciprocal Rank Fusion."""
    scores: dict[int, float] = {}
    chunk_data: dict[int, tuple] = {}

    for rank, row in enumerate(vector_results):
        chunk_id = row[0]
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (rank + k)
        chunk_data[chunk_id] = row

    for rank, row in enumerate(keyword_results):
        chunk_id = row[0]
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (rank + k)
        chunk_data[chunk_id] = row

    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [chunk_data[cid] for cid in ranked_ids[:top_k]]


def find_matching_technique(cur, question: str) -> str | None:
    """Check if the question closely matches a known ATT&CK technique NAME
    directly (not its long description) -- avoids long-text bias where
    an unrelated technique's lengthy description scores higher purely by
    containing more incidental word matches."""
    words = [w for w in question.lower().split() if len(w) > 3]  # skip tiny filler words
    if not words:
        return None

    cur.execute(
        """
        SELECT entity_id, entity_name
        FROM chunks
        WHERE entity_type IN ('technique', 'subtechnique')
          AND lower(entity_name) LIKE ANY(%s)
        LIMIT 1
        """,
        ([f"%{w}%" for w in words],),
    )
    row = cur.fetchone()
    return row[0] if row else None


def graph_lookup(cur, technique_id: str) -> list[tuple]:
    """Given a known technique id, return the chunks for every control
    that officially mitigates it, per entity_links (CTID ground truth)."""
    cur.execute(
        """
        SELECT c.id, c.entity_id, c.entity_type, c.entity_name, c.text
        FROM entity_links el
        JOIN chunks c ON c.entity_id = el.to_entity
        WHERE el.from_entity = %s AND el.link_type = 'mitigates'
        """,
        (technique_id,),
    )
    return cur.fetchall()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "which controls mitigate brute force attacks"
    print(f"Question: {question}\n")

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    query_vector = embed_query(model, question)

    conn = get_connection()
    with conn.cursor() as cur:
        vec_results = vector_search(cur, query_vector)
        kw_results = keyword_search(cur, question)
        fused = reciprocal_rank_fusion(vec_results, kw_results)

        technique_id = find_matching_technique(cur, question)
        graph_results = graph_lookup(cur, technique_id) if technique_id else []

        seen_ids = {r[0] for r in graph_results}
        results = graph_results + [r for r in fused if r[0] not in seen_ids]
        results = results[:5]

    if technique_id:
        print(f"[debug] matched technique: {technique_id}, {len(graph_results)} verified mitigations found\n")

    for chunk_id, entity_id, entity_type, entity_name, text, *_ in results:
        print(f"[{entity_type}] {entity_id} — {entity_name}")
        print(f"  {text[:150]}...")
        print()

    conn.close()