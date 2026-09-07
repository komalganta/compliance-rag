import os
import sys
import psycopg
from dotenv import load_dotenv
from fastembed import TextEmbedding
from app.query import get_connection, embed_query, retrieve

load_dotenv()


def fetch_eval_questions(cur) -> list[tuple]:
    """Load all eval questions from the database."""
    cur.execute("SELECT id, question, gold_entity_ids, category, answerable FROM eval_questions ORDER BY id")
    return cur.fetchall()

def score_question(cur, model, question: str, gold_ids: list[str]) -> tuple[float, list[str]]:
    results = retrieve(cur, model, question)
    retrieved_ids = [r[1] for r in results]

    if not gold_ids:
        return (1.0 if not retrieved_ids else 0.0, retrieved_ids)

    hits = set(retrieved_ids) & set(gold_ids)
    recall = len(hits) / len(gold_ids)
    return recall, retrieved_ids

if __name__ == "__main__":
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    conn = get_connection()

    with conn.cursor() as cur:
        questions = fetch_eval_questions(cur)

        total_recall = 0
        print(f"{'ID':<4} {'Category':<14} {'Recall':<8} Question")
        print("-" * 70)
        for qid, question, gold_ids, category, answerable in questions:
            recall, retrieved = score_question(cur, model, question, gold_ids)
            total_recall += recall
            print(f"{qid:<4} {category:<14} {recall:<8.2f} {question[:45]}")
            if recall < 1.0:
                print(f"     gold:      {gold_ids}")
                print(f"     retrieved: {retrieved}")

        avg_recall = total_recall / len(questions)
        print("-" * 70)
        print(f"Average recall@5+: {avg_recall:.2%} across {len(questions)} questions")

    conn.close()