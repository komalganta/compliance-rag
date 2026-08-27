
-- Security Compliance RAG: core schema (week 1)
-- Target: Neon Postgres (PG 16/17) with pgvector.
-- Run once per database.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- documents: one row per raw source artifact (a file or feed snapshot).
-- content_hash lets the re-ingestion pipeline (later: GitHub Actions cron)
-- skip unchanged sources and gives you a freshness story for free.
-- ---------------------------------------------------------------------------
CREATE TABLE documents (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type   TEXT NOT NULL CHECK (source_type IN (
                      'attack_enterprise',   -- attack-stix-data JSON
                      'nist_800_53',         -- OSCAL rev5 catalog JSON
                      'csf_2_0',             -- CPRT dataset JSON
                      'ctid_mapping',        -- mappings-explorer export
                      'cisa_kev',            -- KEV catalog JSON feed
                      'cisa_advisory'        -- week 2+: advisory HTML
                  )),
    source_url    TEXT NOT NULL,
    title         TEXT NOT NULL,
    version       TEXT,                      -- e.g. 'ATT&CK v18', 'Rev 5', 'CSF 2.0'
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash  TEXT NOT NULL,             -- sha256 of raw payload
    UNIQUE (source_type, source_url, content_hash)
);

-- ---------------------------------------------------------------------------
-- chunks: one row per entity (technique, control, subcategory, KEV entry),
-- split into multiple rows only when an entity exceeds the embedding model's
-- ~512-token window. entity_id is the official identifier and is what the
-- eval harness scores against.
-- embedding dim 384 = bge-small-en-v1.5 (fastembed). Change if you swap models.
-- ---------------------------------------------------------------------------
CREATE TABLE chunks (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_id        BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INT NOT NULL,              -- running order within the document
    entity_type   TEXT NOT NULL,             -- 'technique','subtechnique','mitigation',
                                             -- 'control','control_enhancement',
                                             -- 'csf_subcategory','kev_entry',
                                             -- 'mapping','advisory_section'
    entity_id     TEXT,                      -- 'T1110','T1110.003','AC-7','PR.AA-01','CVE-2026-1234'
    entity_name   TEXT,
    text          TEXT NOT NULL,             -- header line + body, as embedded
    token_count   INT,
    embedding     VECTOR(384),
    tsv           TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    content_hash  TEXT NOT NULL,             -- sha256 of text; resumable embedding pass
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_gin        ON chunks USING gin (tsv);   -- week 2: hybrid/BM25 leg
CREATE INDEX chunks_entity_id_idx  ON chunks (entity_id);
CREATE INDEX chunks_entity_type_idx ON chunks (entity_type);

-- ---------------------------------------------------------------------------
-- entity_links: structured edges between entities. Populated from CTID
-- ATT&CK<->800-53 mappings and ATT&CK STIX relationships (mitigation ->
-- technique). This table is the eval answer key: gold questions are
-- generated from these rows, so retrieval scoring never needs an LLM.
-- ---------------------------------------------------------------------------
CREATE TABLE entity_links (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provenance   TEXT NOT NULL,              -- 'ctid_attack_to_800_53','attack_stix', ...
    from_entity  TEXT NOT NULL,              -- 'T1110'
    to_entity    TEXT NOT NULL,              -- 'AC-7'
    link_type    TEXT NOT NULL,              -- 'mitigates','detects','maps_to'
    UNIQUE (provenance, from_entity, to_entity, link_type)
);

CREATE INDEX entity_links_from_idx ON entity_links (from_entity);
CREATE INDEX entity_links_to_idx   ON entity_links (to_entity);

-- ---------------------------------------------------------------------------
-- eval_questions: the week-3 gold set lives in the same database.
-- answerable = FALSE rows are out-of-scope traps where the correct system
-- behavior is a calibrated refusal.
-- ---------------------------------------------------------------------------
CREATE TABLE eval_questions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question        TEXT NOT NULL,
    gold_entity_ids TEXT[] NOT NULL,         -- entity_ids a correct retrieval must surface
    category        TEXT NOT NULL,           -- 'single_hop','multi_hop','mapping',
                                             -- 'freshness','out_of_scope'
    difficulty      TEXT NOT NULL DEFAULT 'medium',
    answerable      BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT
);