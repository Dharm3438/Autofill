import re
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


# Single source of truth for the physical installation steps tracked per customer.
# Editing this list (add / rename / reorder) automatically flows everywhere because
# stored customer steps are merged against it on every read/write (see merge_steps).
INSTALLATION_STEPS = [
    {"key": "structure", "label": "Solar Structure"},
    {"key": "painting", "label": "Painting / Coating"},
    {"key": "cement_grouting", "label": "Cement Grouting"},
    {"key": "wiring", "label": "Solar Wiring"},
    {"key": "acdb", "label": "ACDB Installation"},
    {"key": "dcdb", "label": "DCDB Installation"},
    {"key": "inverter", "label": "Inverter Installation"},
    {"key": "panels", "label": "Solar Panel Installation"},
    {"key": "generation_meter", "label": "Generation Meter Installation"},
    {"key": "dcr_ready", "label": "DCR Ready"},
    {"key": "document_upload", "label": "Documents Uploaded"},
    {"key": "net_meter", "label": "Net Meter Installation"},
    {"key": "subsidy_received", "label": "Subsidy Received"},
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


def parse_amount(value) -> float:
    """Best-effort parse of a money value into a float.

    SYSTEM_COST is stored as a free-form string (e.g. "1,50,000" or "₹150000"),
    so strip everything except digits and the decimal point. Returns 0 on
    anything unparseable.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def payment_info(customer: dict) -> dict:
    """Normalize a customer's payment fields into total/received/remaining.

    Total comes from SYSTEM_COST (the price quoted in the customer form) and is
    not editable here. Received is the sum of individually dated received-payment
    entries. Tolerates customers created before this feature by falling back to
    the old single `received_payment` value. Remaining never goes negative.
    """
    total = parse_amount(customer.get("SYSTEM_COST"))

    entries = customer.get("received_payments")
    if not entries and customer.get("received_payment"):
        # Legacy single-value record: surface it as one undated entry.
        entries = [{"amount": parse_amount(customer.get("received_payment")), "date": None}]
    entries = entries or []

    received = sum(parse_amount(e.get("amount")) for e in entries if isinstance(e, dict))
    return {
        "total_payment": total,
        "received_payment": received,
        "remaining_payment": max(total - received, 0),
        "received_payments": entries,
    }


class ReceivedPayment(BaseModel):
    amount: float = Field(ge=0)
    date: Optional[str] = None  # "YYYY-MM-DD"


class PaymentUpdate(BaseModel):
    received_payments: List[ReceivedPayment] = Field(default_factory=list)
