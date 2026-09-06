from fastapi import FastAPI
from pydantic import BaseModel
from fastembed import TextEmbedding

from app.query import get_connection
from app.answer import retrieve, build_context, build_prompt, call_groq

app = FastAPI()

# Loaded once at startup, reused for every request -- loading this per-request
# would add several seconds of delay to every single question.
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    answer: str
    sources: list[str]


@app.get("/")
def health_check():
    """A simple endpoint to confirm the server is running."""
    return {"status": "ok"}


@app.post("/ask")
def ask_question(request: QuestionRequest) -> AnswerResponse:
    """Answer a compliance question using the full RAG pipeline
    (vector + keyword + graph retrieval, then Groq-generated,
    citation-grounded answer)."""
    conn = get_connection()
    with conn.cursor() as cur:
        chunks = retrieve(cur, model, request.question)
    conn.close()

    context = build_context(chunks)
    prompt = build_prompt(request.question, context)
    answer_text = call_groq(prompt)

    source_list = [f"{entity_id} — {entity_name}" for _, entity_id, _, entity_name, *_ in chunks]
    return AnswerResponse(answer=answer_text, sources=source_list)