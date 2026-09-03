import json
import re
from pathlib import Path

NIST_PATH = Path("data/raw/nist_800_53_rev5.json")


def load_nist_catalog() -> list[dict]:
    """Load the OSCAL catalog and return a flat list of all top-level
    controls across every family group (AC, AU, CM, etc.)."""
    data = json.loads(NIST_PATH.read_text())
    groups = data["catalog"]["groups"]
    controls = []
    for group in groups:
        controls.extend(group.get("controls", []))
    return controls


def get_control_id(obj: dict) -> str | None:
    """Pull the human-readable control ID (e.g. 'AC-2') from an object's
    props, where name == 'label'."""
    for prop in obj.get("props", []):
        if prop.get("name") == "label":
            return prop.get("value")
    return None


def extract_prose(parts: list[dict]) -> str:
    """Recursively walk a parts list, collecting prose from 'statement'
    and 'item' parts only (skip assessment-objective/guidance parts,
    which restate the same content in auditor-facing phrasing)."""
    texts = []
    for part in parts:
        if part.get("name") in ("statement", "item") and "prose" in part:
            texts.append(part["prose"])
        if "parts" in part:
            texts.append(extract_prose(part["parts"]))
    return " ".join(t for t in texts if t)


def clean_prose(text: str) -> str:
    """Strip OSCAL's {{ insert: param, ... }} placeholder syntax,
    replacing each with a readable stand-in."""
    return re.sub(r"\{\{\s*insert:\s*param,\s*[\w.-]+\s*\}\}", "[organization-defined]", text)


def extract_controls(controls: list[dict], parent_id: str | None = None) -> list[dict]:
    """Recursively extract controls and their nested enhancements into
    flat dicts matching our chunks table shape."""
    extracted = []
    for ctrl in controls:
        control_id = get_control_id(ctrl)
        if control_id is None:
            continue
        prose = extract_prose(ctrl.get("parts", []))
        text = clean_prose(f"{control_id} {ctrl['title']}: {prose}")
        extracted.append({
            "entity_id": control_id,
            "entity_type": "control_enhancement" if "(" in control_id else "control",
            "entity_name": ctrl["title"],
            "text": text,
        })
        if "controls" in ctrl:
            extracted.extend(extract_controls(ctrl["controls"], parent_id=control_id))
    return extracted


if __name__ == "__main__":
    top_level_controls = load_nist_catalog()
    all_controls = extract_controls(top_level_controls)
    print(f"Loaded {len(top_level_controls)} top-level controls")
    print(f"Extracted {len(all_controls)} controls + enhancements total")
    print(all_controls[0])