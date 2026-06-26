from pydantic import BaseModel
from typing import Optional, List, Literal


# Single source of truth for the physical installation steps tracked per customer.
# Editing this list (add / rename / reorder) automatically flows everywhere because
# stored customer steps are merged against it on every read/write (see merge_steps).
INSTALLATION_STEPS = [
    {"key": "structure", "label": "Mounting Structure"},
    {"key": "painting", "label": "Painting / Coating"},
    {"key": "cement_grouting", "label": "Cement Grouting"},
    {"key": "wiring", "label": "DC/AC Wiring"},
    {"key": "acdb", "label": "ACDB Installation"},
    {"key": "dcdb", "label": "DCDB Installation"},
    {"key": "inverter", "label": "Inverter Installation"},
    {"key": "panels", "label": "Solar Panel Installation"},
    {"key": "generation_meter", "label": "Generation Meter Installation"},
]

STEP_KEYS = {s["key"] for s in INSTALLATION_STEPS}
STEP_LABELS = {s["key"]: s["label"] for s in INSTALLATION_STEPS}


def default_installation_steps() -> List[dict]:
    """A fresh set of steps, all pending, in canonical order."""
    return [
        {
            "key": s["key"],
            "status": "pending",
            "completed_date": None,
            "performed_by": None,
            "notes": None,
        }
        for s in INSTALLATION_STEPS
    ]


def merge_steps(stored: Optional[list]) -> List[dict]:
    """
    Reconcile a customer's stored steps against the current INSTALLATION_STEPS:
      • keep existing data (status/date/person/notes) keyed by step key
      • add any new keys as pending
      • drop unknown/removed keys
      • preserve canonical order
    Tolerates customers created before this feature (stored is None) and future
    edits to the step list — no migration needed.
    """
    by_key = {s.get("key"): s for s in (stored or []) if isinstance(s, dict)}
    merged = []
    for s in INSTALLATION_STEPS:
        existing = by_key.get(s["key"]) or {}
        merged.append(
            {
                "key": s["key"],
                "label": s["label"],
                "status": existing.get("status", "pending"),
                "completed_date": existing.get("completed_date"),
                "performed_by": existing.get("performed_by"),
                "notes": existing.get("notes"),
            }
        )
    return merged


def compute_overall_status(steps: List[dict]) -> str:
    """not_started (0 done) / in_progress (some done) / completed (all done)."""
    total = len(steps)
    done = sum(1 for s in steps if s.get("status") == "done")
    if total == 0 or done == 0:
        return "not_started"
    if done == total:
        return "completed"
    return "in_progress"


class InstallationStepUpdate(BaseModel):
    status: Optional[Literal["pending", "done"]] = None
    completed_date: Optional[str] = None  # "YYYY-MM-DD"
    performed_by: Optional[str] = None
    notes: Optional[str] = None
