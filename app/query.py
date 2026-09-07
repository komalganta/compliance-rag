import os
import sys
import re
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


def clean_for_tsquery(text: str) -> str:
    """Strip punctuation, keeping only words, for safe tsquery construction.
    NOTE: this deliberately loses characters like '.' and '-', so it must
    NOT be used for exact entity_id matching (see find_exact_entity_id)."""
    words = re.findall(r"\w+", text)
    return " | ".join(words) if words else ""


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
    or_query = clean_for_tsquery(question)
    if not or_query:
        return []
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
    words = [w for w in re.findall(r"\w+", question.lower()) if len(w) > 3]
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


def find_exact_entity_id(cur, question: str) -> str | None:
    """Check if the question contains a literal entity_id (e.g. 'GV.OC',
    'CVE-2026-82078', 'T1110', 'AC-07') by searching for exact-match
    substrings. Deliberately uses the RAW question text (not the
    punctuation-stripped version from clean_for_tsquery), since IDs like
    'GV.OC' and 'CVE-2026-82078' rely on their dots/hyphens to match."""
    candidates = re.findall(r"[A-Za-z]{2,4}[-\.][\w\.\-\(\)]+|T\d{4}(?:\.\d+)?", question)
    for candidate in candidates:
        candidate = candidate.rstrip("?.,!)")  # trim trailing punctuation caught by the match
        cur.execute("SELECT entity_id FROM chunks WHERE entity_id = %s LIMIT 1", (candidate,))
        row = cur.fetchone()
        if row:
            return row[0]
    return None


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


def lookup_exact_chunk(cur, entity_id: str) -> list[tuple]:
    """Return the single chunk matching an exact entity_id, wrapped as a
    list so it composes the same way as graph_lookup's results."""
    cur.execute(
        "SELECT id, entity_id, entity_type, entity_name, text FROM chunks WHERE entity_id = %s",
        (entity_id,),
    )
    return cur.fetchall()


def retrieve(cur, model, question: str) -> list[tuple]:
    """Run the full retrieval pipeline, in priority order:
    1. Exact entity_id match (e.g. user typed 'GV.OC' or 'CVE-2026-82078') -- highest confidence,
       checked FIRST since it's a literal match, not a guess.
    2. Technique-name match -> graph lookup via entity_links (CTID-verified mitigations) --
       only attempted if no exact ID was found, since fuzzy substring matching on technique
       names (e.g. 'cover' matching 'Discovery') can otherwise produce false positives that
       incorrectly take priority over a correct exact-ID match.
    3. Hybrid (vector + keyword, fused via RRF) -- fills remaining slots, fuzzy/ranked.
    Results from steps 1-2 are never truncated, since they're verified,
    not a ranked guess. Only step 3's contribution is capped at top_k
    (handled inside reciprocal_rank_fusion)."""
    query_vector = embed_query(model, question)
    vec_results = vector_search(cur, query_vector)
    kw_results = keyword_search(cur, question)
    fused = reciprocal_rank_fusion(vec_results, kw_results)

    exact_id = find_exact_entity_id(cur, question)
    technique_id = None if exact_id else find_matching_technique(cur, question)

    verified_results = []
    if exact_id and re.match(r"^T\d{4}", exact_id):
        verified_results = graph_lookup(cur, exact_id)
    elif exact_id:
        verified_results = lookup_exact_chunk(cur, exact_id)
    elif technique_id:
        verified_results = graph_lookup(cur, technique_id)

    seen_ids = {r[0] for r in verified_results}
    results = verified_results + [r for r in fused if r[0] not in seen_ids]
    return results

if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "which controls mitigate brute force attacks"
    print(f"Question: {question}\n")

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    conn = get_connection()

    with conn.cursor() as cur:
        results = retrieve(cur, model, question)

    for chunk_id, entity_id, entity_type, entity_name, text, *_ in results:
        print(f"[{entity_type}] {entity_id} — {entity_name}")
        print(f"  {text[:150]}...")
        print()

    conn.close()