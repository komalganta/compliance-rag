import json
from pathlib import Path

CTID_PATH = Path("data/raw/ctid_mapping.json")


def load_ctid_mappings() -> list[dict]:
    """Load the raw CTID mapping objects list."""
    data = json.loads(CTID_PATH.read_text())
    return data["mapping_objects"]


def extract_ctid_links(mapping_objects: list[dict]) -> list[dict]:
    """Extract real ATT&CK-technique-to-NIST-control mappings, matching
    our entity_links table shape. Skips 'non_mappable' entries -- those
    are techniques CTID explicitly determined have no matching control,
    which is useful documentation but not a link to store."""
    links = []
    for m in mapping_objects:
        if m.get("status") != "complete":
            continue
        technique_id = m.get("attack_object_id")
        control_id = m.get("capability_id")
        link_type = m.get("mapping_type")
        if not (technique_id and control_id and link_type):
            continue
        links.append({
            "provenance": "ctid_attack_to_800_53",
            "from_entity": technique_id,
            "to_entity": control_id,
            "link_type": link_type,
        })
    return links


if __name__ == "__main__":
    mapping_objects = load_ctid_mappings()
    links = extract_ctid_links(mapping_objects)
    print(f"Loaded {len(mapping_objects)} raw mapping objects")
    print(f"Extracted {len(links)} usable technique-to-control links")
    print(links[0])