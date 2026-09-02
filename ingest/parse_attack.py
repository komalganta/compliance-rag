import json
from pathlib import Path

ATTACK_PATH = Path("data/raw/attack_enterprise.json")


def load_stix_objects() -> list[dict]:
    """Load the raw STIX file and return its list of objects."""
    data = json.loads(ATTACK_PATH.read_text())
    return data["objects"]


def get_attack_id(obj: dict) -> str | None:
    """Pull the human-readable ATT&CK ID (e.g. 'T1110') from an object's
    external_references. Returns None if not present (some objects,
    like deprecated ones, may lack this)."""
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def build_id_lookup(objects: list[dict]) -> dict[str, str]:
    """Build a dict mapping STIX internal id -> readable ATT&CK id,
    for every object that has one (techniques, mitigations, groups, etc.)."""
    id_lookup = {}
    for obj in objects:
        attack_id = get_attack_id(obj)
        if attack_id is not None:
            id_lookup[obj["id"]] = attack_id
    return id_lookup

def extract_techniques(objects: list[dict]) -> list[dict]:
    """Pull out just the attack-pattern objects (techniques/sub-techniques),
    with the fields our chunks table cares about."""
    techniques = []
    for obj in objects:
        if obj["type"] != "attack-pattern":
            continue
        attack_id = get_attack_id(obj)
        if attack_id is None:
            continue  # skip deprecated/revoked entries with no real ID
        techniques.append({
            "entity_id": attack_id,
            "entity_type": "subtechnique" if "." in attack_id else "technique",
            "entity_name": obj["name"],
            "text": f"{attack_id} {obj['name']}: {obj.get('description', '')}",
        })
    return techniques

def extract_technique_relationships(objects: list[dict], id_lookup: dict[str, str]) -> list[dict]:
    """Pull relationships where the target is a technique (mitigates/detects),
    resolving both ends to readable ATT&CK IDs via id_lookup."""
    links = []
    for obj in objects:
        if obj["type"] != "relationship":
            continue
        if obj.get("relationship_type") not in ("mitigates", "detects"):
            continue

        source_id = id_lookup.get(obj["source_ref"])
        target_id = id_lookup.get(obj["target_ref"])
        if source_id is None or target_id is None:
            continue  # one end isn't a recognizable object, skip

        links.append({
            "provenance": "attack_stix",
            "from_entity": source_id,
            "to_entity": target_id,
            "link_type": obj["relationship_type"],
        })
    return links

if __name__ == "__main__":
    objects = load_stix_objects()
    lookup = build_id_lookup(objects)
    techniques = extract_techniques(objects)
    links = extract_technique_relationships(objects, lookup)
    print(f"Loaded {len(objects)} objects, {len(lookup)} have ATT&CK IDs")
    print(f"Extracted {len(techniques)} techniques")
    print(f"Extracted {len(links)} technique relationships")
    print(links[0])