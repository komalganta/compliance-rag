import os
import sys
import requests
from dotenv import load_dotenv
from fastembed import TextEmbedding
from app.query import get_connection, embed_query, retrieve

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