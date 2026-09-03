# Architectural decisions

1. 2026-08-24 — Created repo skeleton with ingest/, app/, eval/, data/raw/.
   Reason: Keep ingestion, app logic, and evaluation clearly separated.
- ATT&CK parser scoped to attack-pattern objects only (techniques/sub-techniques); malware, tools, groups, campaigns excluded — no compliance-relevant mappings exist for them in CTID data.
- Relationship extraction limited to "mitigates" and "detects" types, matching what's relevant to a compliance/controls use case.
- Description text still contains (Citation: ...) markers and stray HTML — flagged as a possible pre-embedding cleanup step in week 2.
- NIST 800-53 parser filters extract_prose to 'statement'/'item' parts only, excluding assessment-objective and guidance parts which restate the same content in auditor phrasing — avoids duplicated text in embeddings.
- OSCAL's {{ insert: param, ... }} placeholder syntax replaced with readable "[organization-defined]" stand-in before embedding.