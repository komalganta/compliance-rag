import os
import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg.connect(os.environ["DATABASE_URL"])


def fetch_technique_mitigations(cur, limit: int = 30) -> list[tuple]:
    """Pull `limit` techniques that have at least one verified mitigation,
    along with the full list of controls that mitigate each one."""
    cur.execute(
        """
        SELECT el.from_entity AS technique_id, c.entity_name AS technique_name,
               array_agg(DISTINCT el.to_entity ORDER BY el.to_entity) AS control_ids
        FROM entity_links el
        JOIN chunks c ON c.entity_id = el.from_entity
        WHERE el.link_type = 'mitigates'
        GROUP BY el.from_entity, c.entity_name
        ORDER BY random()
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()

def insert_generated_questions(cur, rows: list[tuple]) -> int:
    """Insert one single_hop eval question per technique."""
    count = 0
    for technique_id, technique_name, control_ids in rows:
        question = f"Which controls mitigate {technique_id} ({technique_name})?"
        cur.execute(
            """
            INSERT INTO eval_questions (question, gold_entity_ids, category, difficulty, answerable, notes)
            VALUES (%s, %s, 'single_hop', 'auto', TRUE, 'Auto-generated from entity_links.')
            """,
            (question, control_ids),
        )
        count += 1
    return count

if __name__ == "__main__":
    conn = get_connection()
    with conn.cursor() as cur:
        rows = fetch_technique_mitigations(cur, limit=30)
        count = insert_generated_questions(cur, rows)
        print(f"Inserted {count} auto-generated single_hop questions")
    conn.commit()
    conn.close()