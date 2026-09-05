# Architectural decisions

1. 2026-08-24 — Created repo skeleton with ingest/, app/, eval/, data/raw/.
   Reason: Keep ingestion, app logic, and evaluation clearly separated.
- ATT&CK parser scoped to attack-pattern objects only (techniques/sub-techniques); malware, tools, groups, campaigns excluded — no compliance-relevant mappings exist for them in CTID data.
- Relationship extraction limited to "mitigates" and "detects" types, matching what's relevant to a compliance/controls use case.
- Description text still contains (Citation: ...) markers and stray HTML — flagged as a possible pre-embedding cleanup step in week 2.
- NIST 800-53 parser filters extract_prose to 'statement'/'item' parts only, excluding assessment-objective and guidance parts which restate the same content in auditor phrasing — avoids duplicated text in embeddings.
- OSCAL's {{ insert: param, ... }} placeholder syntax replaced with readable "[organization-defined]" stand-in before embedding.
- CSF 2.0 catalog has 34 categories / 185 subcategories in this dataset — differs from commonly-cited 22/106 figures, likely from an earlier CSF draft; verified by manual count against raw JSON.
- CTID mapping file contained 50 duplicate technique-to-control pairs (same provenance/from_entity/to_entity/link_type); entity_links' UNIQUE constraint + ON CONFLICT DO NOTHING deduplicated them automatically. Verified count: 5,314 extracted -> 5,264 unique links stored. Final loaded totals: 3,960 chunks, 5,264 entity_links.
- fastembed returns NumPy arrays; psycopg needs pgvector's register_vector() plus .tolist() conversion to write them into a VECTOR column.
- Used bge-small-en-v1.5 (384-dim) via fastembed, chosen for CPU-friendly local embedding with no API costs.
- Ground-truth check: queried entity_links for T1110 (brute force) mitigations via CTID mappings — real answer includes AC-02, AC-03, AC-05, AC-06, AC-07, AC-20, CA-07, CM-02, and more.
- Vector-only search on "which controls mitigate brute force attacks" returned 0/5 of these in its top 5 — surfaced tangentially related controls (SA-05(01), SI-10(06), AC-04(04), AU-09(03)) instead.
- Root cause: embedding model captures general semantic similarity, not precise domain-term matching; formal control language ("Unsuccessful Logon Attempts") doesn't share vocabulary with plain-English attack descriptions ("brute force").
- Motivates week 2 work: hybrid retrieval (vector + keyword/BM25 search using the tsv column already in chunks) and/or graph-based retrieval using entity_links directly for known technique IDs.
- Fixed find_matching_technique: originally used ts_rank on full chunk text, which favored techniques with longer descriptions over exact name matches (T1558.003 outranked T1110 "Brute Force" despite T1110 being the obvious match). Fixed by matching directly against entity_name with LIKE, bypassing text-length bias entirely.
- Verified: "which controls mitigate brute force attacks" now correctly matches T1110 and returns AC-02, AC-03, AC-05, AC-06, AC-07 — matching CTID ground truth.