# Compliance RAG Assistant

**Live demo:** https://compliance-rag-k8np.onrender.com/docs

A retrieval-augmented generation (RAG) system that answers cybersecurity compliance questions, grounded in NIST 800-53, NIST CSF 2.0, MITRE ATT&CK, and CISA's Known Exploited Vulnerabilities catalog, and also cites its sources on every claim.

**Try it from a terminal:**
```bash
curl -X POST https://compliance-rag-k8np.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "which controls mitigate brute force attacks"}'
```

**Sample response:**
```json
{
  "answer": "Brute-force attacks are mitigated by AC-07 – Unsuccessful Logon Attempts, which enforces a limit on consecutive invalid logon attempts... [5]",
  "sources": ["AC-02 — Account Management", "AC-03 — Access Enforcement", "AC-05 — Separation of Duties", "AC-06 — Least Privilege", "AC-07 — Unsuccessful Logon Attempts"]
}
```

---

## What it does

Ask a plain-English compliance question: "which controls mitigate brute force attacks?", and the system retrieves the relevant, verified passages from four official government/MITRE sources, then generates a written answer that cites exactly which control or technique each claim came from. If the retrieved sources don't actually contain the answer, it says so explicitly instead of guessing.

## Architecture

```
Download → Parse → Load → Embed → Retrieve → Generate → Deploy
```

| Stage | What happens |
|---|---|
| **Download** | Pull 5 source files from official repos (MITRE, NIST, CISA), fingerprint each with SHA-256 for change detection |
| **Parse** | 5 separate parsers, since each source uses a genuinely different format: STIX (ATT&CK), OSCAL (NIST 800-53, CSF 2.0), and flat JSON (CISA KEV) |
| **Load** | Structured entities → PostgreSQL (`chunks` table); verified technique-to-control relationships → `entity_links` table |
| **Embed** | Each chunk's text → 384-dim vector via `fastembed` (bge-small-en-v1.5), stored in Postgres via `pgvector` |
| **Retrieve** | Three-layer hybrid retrieval (see below) |
| **Generate** | Retrieved chunks + question → Groq (Llama-family model) → cited, grounded answer |
| **Deploy** | FastAPI wrapping the whole pipeline, deployed on Render |

### Retrieval: three layers, in priority order

1. **Exact-ID lookup** — if the question names a specific ID (`GV.OC`, `CVE-2026-82078`, `T1110`), match it directly. Technique IDs route through the knowledge graph (step 2); everything else returns its chunk directly.
2. **Knowledge-graph lookup** — when a question names or matches an ATT&CK technique, its real, MITRE/CTID-verified mitigations are pulled directly from `entity_links` — no guessing, no vocabulary matching, just a lookup against 5,264 official relationships.
3. **Hybrid fuzzy search** — vector similarity (meaning-based) and Postgres full-text keyword search (exact-term-based), merged via Reciprocal Rank Fusion, filling in whatever the first two layers didn't cover.

This design exists because layer 3 alone was not good enough.

## Eval results

**97.14% recall@5** across 35 test questions (100% on the 34 questions where recall is a valid metric — see note below), scored against ground truth pulled directly from CTID's official ATT&CK-to-NIST-800-53 mappings.

- 5 hand-crafted questions, covering single-hop lookups, multi-hop reasoning, out-of-scope refusal, and cross-source (CSF/KEV) retrieval
- 30 auto-generated questions, randomly sampled from the 5,264 verified technique-to-control mappings — each question's gold answer comes straight from the data itself, so there's no manual grading involved and no cherry-picking

*Why not 35/35: one question tests refusal behavior on a genuinely unanswerable question ("what's the projected 2027 cybersecurity spending?"). Recall@5 isn't a meaningful metric there, since fuzzy search always returns its closest matches regardless of true relevance — refusal is a generation-layer behavior, verified manually, not yet scored automatically.*

### The story behind that number

Vector-search-only retrieval, tested first, got **1 out of 5 correct results** on a straightforward "which controls mitigate brute force attacks" question: it surfaced correct-sounding but wrong controls, missing the actual textbook answer (`AC-07: Unsuccessful Logon Attempts`) entirely, because the control's own text never uses the words "brute" or "force." That gap between how people ask questions and how compliance documents are actually written is the reason this system has three retrieval layers instead of one.

Building the eval harness itself then surfaced four more real bugs:
- A hardcoded `results[:5]` truncation was silently dropping correct answers even after the knowledge-graph layer had found them (recall on one question: 36% → 100% after a one-line fix)
- A parser bug where NIST's ID-extraction logic was reused for CSF data, which stores IDs differently — corrupting every CSF entity's ID
- A prompt/data-phrasing issue that caused the model to state a real KEV vulnerability *wasn't* KEV-listed
- A retrieval priority-ordering bug, found only after consolidating three duplicate copies of the retrieval logic into one function — fuzzy technique-name matching could false-positive on common words (e.g. "cover" matching "Discovery"), a bug invisible until the code was unified enough to actually catch it consistently

Every one of these is documented, with root cause and fix, in [`DECISIONS.md`](./DECISIONS.md).

## Known limitations

- **No true multi-hop reasoning.** A question requiring two techniques' mitigations to be intersected currently detects only one technique per question. It correctly refuses rather than fabricating an answer, but doesn't solve the underlying question. Documented, not yet fixed.
- **Recall@5 can't score refusal correctness** — that requires checking the LLM's generated text, not retrieval output. Verified manually; not yet automated.
- **Free-tier hosting** means cold starts after idle periods (see top of this README).

## Tech stack

Python · PostgreSQL + pgvector · FastAPI · fastembed (bge-small-en-v1.5) · Groq (Llama) · Render

## Local setup

```bash
git clone https://github.com/komalganta/compliance-rag.git
cd compliance-rag
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with:
```
DATABASE_URL=postgresql://...
GROQ_API_KEY=...
```

Then run the pipeline in order:
```bash
python ingest/download.py
python -m ingest.load_db
python ingest/embed_chunks.py
python -m eval.run_eval        # optional: verify retrieval quality
uvicorn app.main:app --reload  # start the API locally
```

## Future Work To Be Done:

- Expand the eval set further and add automated refusal-correctness scoring
- A lightweight agentic layer for live CVE/KEV lookups outside the static corpus
- Cleanup pass on remaining known issues (citation bracket formatting, entity-type filtering in hybrid results)

---