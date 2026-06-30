import re
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


# Single source of truth for the physical installation steps tracked per customer.
# Editing this list (add / rename / reorder) automatically flows everywhere because
# stored customer steps are merged against it on every read/write (see merge_steps).
# `short` is the abbreviation shown inside the status circles on the
# installation list (red = pending, green = done). Keep them unique.
INSTALLATION_STEPS = [
    {"key": "structure", "label": "Solar Structure", "short": "S"},
    {"key": "painting", "label": "Painting / Coating", "short": "C"},
    {"key": "cement_grouting", "label": "Cement Grouting", "short": "G"},
    {"key": "wiring", "label": "Solar Wiring", "short": "W"},
    {"key": "earthing_la", "label": "Earthing + LA", "short": "EL"},
    {"key": "acdb", "label": "ACDB Installation", "short": "A"},
    {"key": "dcdb", "label": "DCDB Installation", "short": "D"},
    {"key": "inverter", "label": "Inverter Installation", "short": "I"},
    {"key": "panels", "label": "Solar Panel Installation", "short": "P"},
    {"key": "generation_meter", "label": "Generation Meter Installation", "short": "M"},
    {"key": "dcr_ready", "label": "DCR Ready", "short": "DR"},
    {"key": "document_upload", "label": "Documents Uploaded", "short": "DU"},
    {"key": "net_meter", "label": "Net Meter Installation", "short": "N"},
    {"key": "subsidy_received", "label": "Subsidy Received", "short": "SR"},
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
                "short": s["short"],
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


class SerialsUpdate(BaseModel):
    """Inverter / panel serial numbers entered on the installation page.

    The installation date is NOT accepted here — it is derived from the dates
    these serials were filled in (see compute_serials_update).
    """
    INVERTER_SR_NO: Optional[str] = None
    PANEL_SR_NO: Optional[str] = None


def _stamp_serial(new_val: Optional[str], old_val: Optional[str],
                  prior_date: Optional[str], fallback_date: Optional[str],
                  today: str) -> tuple[str, Optional[str]]:
    """Resolve a serial's stored value and the date it was set.

    Returns (clean_value, set_date):
      • blank value          → ("", None)            — no date recorded
      • value changed        → (value, today)        — stamped now
      • value unchanged      → (value, prior_date or fallback_date or today)

    `fallback_date` lets a customer created before this feature (serial already
    filled, but no recorded set-date) keep their existing INSTALLATION_DATE
    instead of being re-stamped to today on the first save.
    """
    new_clean = (new_val or "").strip()
    if not new_clean:
        return "", None
    old_clean = (old_val or "").strip()
    effective_prior = prior_date or fallback_date
    if new_clean != old_clean or not effective_prior:
        return new_clean, today
    return new_clean, effective_prior


def compute_serials_update(customer: dict, body: "SerialsUpdate", today: str) -> dict:
    """Build the $set fields for a serials update.

    Stamps each serial's set-date, then derives INSTALLATION_DATE as the LATEST
    of the two set-dates — but only when BOTH serials are filled. If either is
    blank the installation date is cleared (""), which keeps document generation
    blocked until the installation is genuinely complete.
    """
    inv_val, inv_date = _stamp_serial(
        body.INVERTER_SR_NO, customer.get("INVERTER_SR_NO"),
        customer.get("inverter_sr_set_date"), customer.get("INSTALLATION_DATE"), today,
    )
    pan_val, pan_date = _stamp_serial(
        body.PANEL_SR_NO, customer.get("PANEL_SR_NO"),
        customer.get("panel_sr_set_date"), customer.get("INSTALLATION_DATE"), today,
    )

    # Installation date only exists once BOTH serials are filled; take the later
    # of the two dates they were entered on.
    if inv_val and pan_val and inv_date and pan_date:
        installation_date = max(inv_date, pan_date)
    else:
        installation_date = ""

    return {
        "INVERTER_SR_NO": inv_val,
        "PANEL_SR_NO": pan_val,
        "inverter_sr_set_date": inv_date,
        "panel_sr_set_date": pan_date,
        "INSTALLATION_DATE": installation_date,
    }
