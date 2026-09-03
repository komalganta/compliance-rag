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