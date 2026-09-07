import os
import sys
import requests
from dotenv import load_dotenv
from fastembed import TextEmbedding

from app.query import (
    get_connection,
    embed_query,
    vector_search,
    keyword_search,
    reciprocal_rank_fusion,
    find_matching_technique,
    graph_lookup,
)

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"

def build_context(chunks: list[tuple]) -> str:
    """Turn retrieved chunks into a numbered, labeled text block for the prompt."""
    lines = []
    for i, (chunk_id, entity_id, entity_type, entity_name, text, *_) in enumerate(chunks, start=1):
        lines.append(f"[{i}] ({entity_id} - {entity_name}): {text}")
    return "\n\n".join(lines)

def build_prompt(question: str, context: str) -> str:
    return f"""You are a cybersecurity compliance assistant. Answer the question using ONLY the information in the numbered sources below. Do not use any outside knowledge.

For every claim you make, cite the source number(s) in square brackets, like [1] or [1][3].

If multiple sources are relevant to the question, synthesize them into a complete answer rather than picking just one.

If the sources do not contain enough information to answer the question, say so explicitly instead of guessing.

Sources:
{context}

Question: {question}

Answer:"""

def call_groq(prompt: str) -> str:
    """Send the prompt to Groq's chat completion API, return the model's answer text."""
    response = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def retrieve(cur, model, question: str, top_k: int = 5) -> list[tuple]:
    """Run full three-layer retrieval pipeline. Graph-verified results
    from entity_links are never truncated, since they're confirmed
    ground truth, not ranked guess. Only fuzzy hybrid (vector+keyword)
    results are capped at top_k, to fill in when no graph match exists."""
    query_vector = embed_query(model, question)

    vec_results = vector_search(cur, query_vector)
    kw_results = keyword_search(cur, question)
    fused = reciprocal_rank_fusion(vec_results, kw_results, top_k=top_k)

    technique_id = find_matching_technique(cur, question)
    graph_results = graph_lookup(cur, technique_id) if technique_id else []

    seen_ids = {r[0] for r in graph_results}
    results = graph_results + [r for r in fused if r[0] not in seen_ids]
    return results


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "which controls mitigate brute force attacks"
    print(f"Question: {question}\n")

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    conn = get_connection()

    with conn.cursor() as cur:
        chunks = retrieve(cur, model, question)

    conn.close()

    context = build_context(chunks)
    prompt = build_prompt(question, context)
    answer = call_groq(prompt)

    print("Answer:")
    print(answer)
    print("\n--- Sources ---")
    for i, (chunk_id, entity_id, entity_type, entity_name, text, *_) in enumerate(chunks, start=1):
        print(f"[{i}] {entity_id} — {entity_name}")