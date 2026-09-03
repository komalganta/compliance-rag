import json
from pathlib import Path

CSF_PATH = Path("data/raw/csf_2_0.json")

# CSF's OSCAL "class" field tells us the tier directly, so we map it
# straight to our entity_type values instead of guessing from ID shape.
CLASS_TO_ENTITY_TYPE = {
    "category": "csf_category",
    "subcategory": "csf_subcategory",
}


def load_csf_catalog() -> list[dict]:
    """Load the CSF OSCAL catalog and return the top-level Function groups
    (GV, ID, PR, DE, RS, RC), each containing Category controls."""
    data = json.loads(CSF_PATH.read_text())
    return data["catalog"]["groups"]


def get_control_id(obj: dict) -> str | None:
    """Pull the human-readable ID (e.g. 'GV.OC' or 'GV.OC-01') from an
    object's props, where name == 'label'."""
    for prop in obj.get("props", []):
        if prop.get("name") == "label":
            return prop.get("value")
    return None


def extract_prose(parts: list[dict]) -> str:
    """Collect prose from 'statement' parts only (skip 'example' parts,
    which are illustrative and not part of the core control text)."""
    texts = []
    for part in parts:
        if part.get("name") == "statement" and "prose" in part:
            texts.append(part["prose"])
    return " ".join(texts)


def extract_csf_controls(functions: list[dict]) -> list[dict]:
    """Walk Function -> Category -> Subcategory, extracting each Category
    and Subcategory as a flat chunk-shaped dict. Functions themselves
    (GV, ID, PR, DE, RS, RC) are not embedded as separate entities --
    they're broad umbrellas, not queryable controls."""
    extracted = []
    for function in functions:
        categories = function.get("controls", [])
        for category in categories:
            cat_id = get_control_id(category)
            if cat_id is None:
                continue
            cat_prose = extract_prose(category.get("parts", []))
            extracted.append({
                "entity_id": cat_id,
                "entity_type": "csf_category",
                "entity_name": category["title"],
                "text": f"{cat_id} {category['title']}: {cat_prose}",
            })

            subcategories = category.get("controls", [])
            for sub in subcategories:
                sub_id = get_control_id(sub)
                if sub_id is None:
                    continue
                sub_prose = extract_prose(sub.get("parts", []))
                extracted.append({
                    "entity_id": sub_id,
                    "entity_type": "csf_subcategory",
                    "entity_name": sub.get("title", sub_id),
                    "text": f"{sub_id}: {sub_prose}",
                })
    return extracted


if __name__ == "__main__":
    functions = load_csf_catalog()
    all_entries = extract_csf_controls(functions)
    categories = [e for e in all_entries if e["entity_type"] == "csf_category"]
    subcategories = [e for e in all_entries if e["entity_type"] == "csf_subcategory"]
    print(f"Loaded {len(functions)} top-level Functions")
    print(f"Extracted {len(categories)} categories, {len(subcategories)} subcategories")
    print(subcategories[0])