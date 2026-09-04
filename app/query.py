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


def search(cur, query_vector: list[float], top_k: int = 5) -> list[tuple]:
    """Find the top_k chunks closest in meaning to the query vector."""
    cur.execute(
        """
        SELECT entity_id, entity_type, entity_name, text, embedding <=> %s::vector AS distance
        FROM chunks
        ORDER BY distance
        LIMIT %s
        """,
        (query_vector, top_k),
    )
    return cur.fetchall()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "which controls mitigate brute force attacks"
    print(f"Question: {question}\n")

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    query_vector = embed_query(model, question)

    conn = get_connection()
    with conn.cursor() as cur:
        results = search(cur, query_vector)

    for entity_id, entity_type, entity_name, text, distance in results:
        print(f"[{entity_type}] {entity_id} — {entity_name}  (distance: {distance:.3f})")
        print(f"  {text[:150]}...")
        print()

    conn.close()