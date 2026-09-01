import hashlib
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

RAW_DIR = Path("data/raw")
MANIFEST_PATH = RAW_DIR / "manifest.json"

SOURCES = [
    {
        "source_type": "attack_enterprise",
        "url": "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json",
        "filename": "attack_enterprise.json",
    },
    {
        "source_type": "nist_800_53",
        "url": "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
        "filename": "nist_800_53_rev5.json",
    },
    {
        "source_type": "cisa_kev",
        "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        "filename": "cisa_kev.json",
    },
    {
        "source_type": "csf_2_0",
        "url": "https://raw.githubusercontent.com/usnistgov/oscal-content/refs/heads/main/nist.gov/CSF/v2.0/json/NIST_CSF_v2.0_catalog.json",
        "filename": "csf_2_0.json",
    },
    {
        "source_type": "ctid_mapping",
        "url": "https://raw.githubusercontent.com/center-for-threat-informed-defense/mappings-explorer/refs/heads/main/mappings/nist_800_53/attack-16.1/nist_800_53-rev5/enterprise/nist_800_53-rev5_attack-16.1-enterprise.json",
        "filename": "ctid_mapping.json",
    }
]

def download_file(url: str, dest_path: Path) -> bytes:
    """Download url, save raw bytes to dest_path, return the bytes."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    return response.content

def compute_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of the given bytes."""
    return hashlib.sha256(data).hexdigest()

def build_manifest_entry(source: dict, content_hash: str) -> dict:
    """Build one manifest record for a downloaded source."""
    return {
        "source_type": source["source_type"],
        "source_url": source["url"],
        "filename": source["filename"],
        "content_hash": content_hash,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for source in SOURCES:
        print(f"Downloading {source['source_type']}...")
        dest_path = RAW_DIR / source["filename"]
        content = download_file(source["url"], dest_path)
        content_hash = compute_hash(content)
        manifest.append(build_manifest_entry(source, content_hash))
        print(f"  saved to {dest_path}, hash {content_hash[:12]}...")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()