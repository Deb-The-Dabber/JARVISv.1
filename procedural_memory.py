import difflib
import json
import os

PROCEDURES_PATH = os.path.join(os.path.expanduser("~"), "jarvis_procedures.json")


def _load() -> list:
    if not os.path.exists(PROCEDURES_PATH):
        return []
    try:
        with open(PROCEDURES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(procedures: list):
    with open(PROCEDURES_PATH, "w", encoding="utf-8") as f:
        json.dump(procedures, f, indent=2)


def save_procedure(trigger: str, steps: list, description: str = ""):
    procedures = [p for p in _load() if p.get("trigger", "").lower() != trigger.lower()]
    procedure = {
        "trigger": trigger,
        "steps": steps,
        "description": description,
    }
    procedures.append(procedure)
    _save(procedures)


def get_procedure(trigger: str) -> dict:
    procedures = _load()
    if not procedures:
        return None
    trigger_l = trigger.lower().strip()
    for procedure in procedures:
        saved = procedure.get("trigger", "").lower()
        if saved == trigger_l or saved in trigger_l:
            return procedure

    matches = difflib.get_close_matches(
        trigger_l,
        [p.get("trigger", "").lower() for p in procedures],
        n=1,
        cutoff=0.75,
    )
    if not matches:
        return None
    for procedure in procedures:
        if procedure.get("trigger", "").lower() == matches[0]:
            return procedure
    return None


def list_procedures() -> str:
    procedures = _load()
    if not procedures:
        return ""
    lines = []
    for procedure in procedures:
        desc = procedure.get("description") or f"{len(procedure.get('steps', []))} steps"
        lines.append(f"{procedure.get('trigger')}: {desc}")
    return "\n".join(lines)


def delete_procedure(trigger: str):
    procedures = _load()
    kept = [p for p in procedures if p.get("trigger", "").lower() != trigger.lower()]
    _save(kept)


def detect_procedure_trigger(text: str) -> dict:
    return get_procedure(text)
