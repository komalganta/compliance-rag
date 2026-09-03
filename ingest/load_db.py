import os
import json
import hashlib
from pathlib import Path
import psycopg
from dotenv import load_dotenv

from ingest.parse_attack import load_stix_objects, build_id_lookup, extract_techniques
from ingest.parse_nist import load_nist_catalog, extract_controls
from ingest.parse_csf import load_csf_catalog, extract_csf_controls
from ingest.parse_kev import load_kev_catalog, extract_kev_entries
from ingest.parse_ctid import load_ctid_mappings, extract_ctid_links

load_dotenv()

MANIFEST_PATH = Path("data/raw/manifest.json")


def get_connection():
    """Open a connection to the Neon Postgres database."""
    return psycopg.connect(os.environ["DATABASE_URL"])


def insert_document(cur, source_type: str, source_url: str, title: str, content_hash: str) -> int:
    """Insert one row into documents, return its auto-generated id."""
    cur.execute(
        """
        INSERT INTO documents (source_type, source_url, title, content_hash)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (source_type, source_url, title, content_hash),
    )
    return cur.fetchone()[0]


def load_manifest() -> list[dict]:
    """Load the manifest written by download.py."""
    return json.loads(MANIFEST_PATH.read_text())


def insert_all_documents(cur) -> dict[str, int]:
    """Insert one documents row per manifest entry.
    Returns a dict mapping source_type -> doc_id, so later steps know
    which doc_id to attach to each source's chunks."""
    manifest = load_manifest()
    doc_ids = {}
    for entry in manifest:
        doc_id = insert_document(
            cur,
            source_type=entry["source_type"],
            source_url=entry["source_url"],
            title=entry["source_type"],
            content_hash=entry["content_hash"],
        )
        doc_ids[entry["source_type"]] = doc_id
    return doc_ids


def insert_chunks(cur, doc_id: int, entries: list[dict]) -> int:
    """Insert a list of parsed entities (all sharing the same
    entity_id/entity_type/entity_name/text shape) as chunks tied to
    one document. Returns how many were inserted."""
    for i, entry in enumerate(entries):
        content_hash = hashlib.sha256(entry["text"].encode()).hexdigest()
        cur.execute(
            """
            INSERT INTO chunks (doc_id, chunk_index, entity_type, entity_id, entity_name, text, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (doc_id, i, entry["entity_type"], entry["entity_id"], entry["entity_name"], entry["text"], content_hash),
        )
    return len(entries)

def insert_links(cur, links: list[dict]) -> int:
    """Insert a list of entity_links rows (technique-to-control mappings)."""
    for link in links:
        cur.execute(
            """
            INSERT INTO entity_links (provenance, from_entity, to_entity, link_type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (link["provenance"], link["from_entity"], link["to_entity"], link["link_type"]),
        )
    return len(links)


if __name__ == "__main__":
    conn = get_connection()
    with conn.cursor() as cur:
        doc_ids = insert_all_documents(cur)
        print("Inserted documents:", doc_ids)

        attack_objects = load_stix_objects()
        techniques = extract_techniques(attack_objects)
        n = insert_chunks(cur, doc_ids["attack_enterprise"], techniques)
        print(f"Inserted {n} ATT&CK technique chunks")

        nist_controls = load_nist_catalog()
        controls = extract_controls(nist_controls)
        n = insert_chunks(cur, doc_ids["nist_800_53"], controls)
        print(f"Inserted {n} NIST 800-53 chunks")

        csf_functions = load_csf_catalog()
        csf_entries = extract_csf_controls(csf_functions)
        n = insert_chunks(cur, doc_ids["csf_2_0"], csf_entries)
        print(f"Inserted {n} CSF 2.0 chunks")

        kev_vulns = load_kev_catalog()
        kev_entries = extract_kev_entries(kev_vulns)
        n = insert_chunks(cur, doc_ids["cisa_kev"], kev_entries)
        print(f"Inserted {n} KEV chunks")

        ctid_mappings = load_ctid_mappings()
        links = extract_ctid_links(ctid_mappings)
        n = insert_links(cur, links)
        print(f"Inserted {n} CTID entity_links")

    conn.commit()
    conn.close()