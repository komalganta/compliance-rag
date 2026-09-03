import json
from pathlib import Path

KEV_PATH = Path("data/raw/cisa_kev.json")


def load_kev_catalog() -> list[dict]:
    """Load the raw CISA KEV catalog and return the list of vulnerabilities."""
    data = json.loads(KEV_PATH.read_text())
    return data["vulnerabilities"]


def extract_kev_entries(vulns: list[dict]) -> list[dict]:
    """Convert each KEV entry into a chunk-shaped dict. Every field here
    is already flat -- no nesting, no ID-hunting needed, unlike the other
    three sources."""
    extracted = []
    for v in vulns:
        cve_id = v.get("cveID")
        if cve_id is None:
            continue
        cwes = ", ".join(v.get("cwes") or []) or "none listed"
        text = (
            f"{cve_id} ({v.get('vendorProject', '')} {v.get('product', '')}): "
            f"{v.get('vulnerabilityName', '')}. {v.get('shortDescription', '')} "
            f"Known ransomware use: {v.get('knownRansomwareCampaignUse', 'Unknown')}. "
            f"CWEs: {cwes}. Added to KEV catalog {v.get('dateAdded', '')}, "
            f"remediation due {v.get('dueDate', '')}."
        )
        extracted.append({
            "entity_id": cve_id,
            "entity_type": "kev_entry",
            "entity_name": v.get("vulnerabilityName", cve_id),
            "text": text,
        })
    return extracted


if __name__ == "__main__":
    vulns = load_kev_catalog()
    entries = extract_kev_entries(vulns)
    print(f"Loaded {len(vulns)} KEV vulnerabilities")
    print(f"Extracted {len(entries)} entries")
    print(entries[0])