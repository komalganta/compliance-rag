import os
import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv
from fastembed import TextEmbedding

load_dotenv()

BATCH_SIZE = 100


def get_connection():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def fetch_unembedded_chunks(cur, limit: int) -> list[tuple[int, str]]:
    """Get chunks that don't have an embedding yet, up to `limit` at a time."""
    cur.execute(
        "SELECT id, text FROM chunks WHERE embedding IS NULL LIMIT %s",
        (limit,),
    )
    return cur.fetchall()


def update_embeddings(cur, ids: list[int], vectors) -> None:
    """Write each computed vector back to its chunk row."""
    for chunk_id, vector in zip(ids, vectors):
        cur.execute(
            "UPDATE chunks SET embedding = %s WHERE id = %s",
            (vector.tolist(), chunk_id),
        )


if __name__ == "__main__":
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    conn = get_connection()

    total_done = 0
    while True:
        with conn.cursor() as cur:
            rows = fetch_unembedded_chunks(cur, BATCH_SIZE)
            if not rows:
                break

            ids = [r[0] for r in rows]
            texts = [r[1] for r in rows]
            vectors = list(model.embed(texts))

            update_embeddings(cur, ids, vectors)
        conn.commit()

        total_done += len(rows)
        print(f"Embedded {total_done} chunks so far...")

    conn.close()
    print("Done.")