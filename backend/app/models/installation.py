import re
from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


# Single source of truth for the physical installation steps tracked per customer.
# Editing this list (add / rename / reorder) automatically flows everywhere because
# stored customer steps are merged against it on every read/write (see merge_steps).
# `short` is the abbreviation shown inside the status circles on the
# installation list (red = pending, green = done). Keep them unique.
# `group` (optional) bundles steps that are done together by the same person:
# they keep individual done/pending checkboxes but share one completed date and
# one "done by" (see INSTALLATION_STEP_GROUPS). Grouped steps must be adjacent.
INSTALLATION_STEPS = [
    {"key": "structure", "label": "Solar Structure", "short": "S"},
    {"key": "painting", "label": "Painting / Coating", "short": "C"},
    {"key": "cement_grouting", "label": "Cement Grouting", "short": "G"},
    {"key": "wiring", "label": "Solar Wiring", "short": "W", "group": "wiring"},
    {"key": "earthing_la", "label": "Earthing + LA", "short": "EL", "group": "wiring"},
    {"key": "acdb", "label": "ACDB Installation", "short": "A", "group": "wiring"},
    {"key": "dcdb", "label": "DCDB Installation", "short": "D", "group": "wiring"},
    {"key": "generation_meter", "label": "Generation Meter Installation", "short": "M", "group": "wiring"},
    {"key": "inverter", "label": "Inverter Installation", "short": "I"},
    {"key": "panels", "label": "Solar Panel Installation", "short": "P"},
    {"key": "dcr_ready", "label": "DCR Ready", "short": "DR"},
    {"key": "document_upload", "label": "Documents Uploaded", "short": "DU"},
    {"key": "net_meter", "label": "Net Meter Installation", "short": "N"},
    {"key": "subsidy_received", "label": "Subsidy Received", "short": "SR"},
]

STEP_KEYS = {s["key"] for s in INSTALLATION_STEPS}
STEP_LABELS = {s["key"]: s["label"] for s in INSTALLATION_STEPS}

INSTALLATION_STEP_GROUPS = [
    {"key": "wiring", "label": "Wiring & Electrical"},
]
GROUP_KEYS = {g["key"] for g in INSTALLATION_STEP_GROUPS}
GROUP_LABELS = {g["key"]: g["label"] for g in INSTALLATION_STEP_GROUPS}


def group_step_keys(group_key: str) -> List[str]:
    """Member step keys of a group, in canonical order."""
    return [s["key"] for s in INSTALLATION_STEPS if s.get("group") == group_key]


def default_installation_steps() -> List[dict]:
    """A fresh set of steps, all pending, in canonical order."""
    return [
        {
            "key": s["key"],
            "status": "pending",
            "completed_date": None,
            "performed_by": None,
        }
        for s in INSTALLATION_STEPS
    ]


def merge_steps(stored: Optional[list]) -> List[dict]:
    """
    Reconcile a customer's stored steps against the current INSTALLATION_STEPS:
      • keep existing data (status/date/person) keyed by step key
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
                "group": s.get("group"),
                "group_label": GROUP_LABELS.get(s.get("group")),
                "status": existing.get("status", "pending"),
                "completed_date": existing.get("completed_date"),
                "performed_by": existing.get("performed_by"),
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


# The checklist steps whose completion dates drive INSTALLATION_DATE.
INSTALLATION_DATE_STEP_KEYS = ("inverter", "panels")


def compute_installation_date(steps: List[dict]) -> str:
    """Derive INSTALLATION_DATE from the checklist.

    It is the completed date of the Inverter Installation and Solar Panel
    Installation steps — whichever is present. If only one of the two has a
    date, that date is used; if both are present, the later of the two wins.
    Blank until at least one of them is marked done with a date.

    Completed dates are ISO strings (YYYY-MM-DD), so lexical max == latest.
    """
    dates = [
        s["completed_date"]
        for s in steps
        if s.get("key") in INSTALLATION_DATE_STEP_KEYS and s.get("completed_date")
    ]
    return max(dates) if dates else ""


class InstallationStepUpdate(BaseModel):
    status: Optional[Literal["pending", "done"]] = None
    completed_date: Optional[str] = None  # "YYYY-MM-DD"
    performed_by: Optional[str] = None


class InstallationGroupUpdate(BaseModel):
    """Save a whole step group at once: which members are done, plus the one
    completed date and "done by" shared by every done member."""
    done_keys: List[str] = Field(default_factory=list)
    completed_date: Optional[str] = None  # "YYYY-MM-DD"
    performed_by: Optional[str] = None


def apply_group_update(steps: List[dict], group_key: str, body: "InstallationGroupUpdate") -> None:
    """Mutate merged `steps` in place for a group save.

    Done members all get the same date (default today) and person; members not
    in `done_keys` go back to pending with their details cleared."""
    members = set(group_step_keys(group_key))
    done = set(body.done_keys) & members
    shared_date = body.completed_date or date.today().isoformat()
    for s in steps:
        if s["key"] not in members:
            continue
        if s["key"] in done:
            s["status"] = "done"
            s["completed_date"] = shared_date
            s["performed_by"] = body.performed_by or None
        else:
            s["status"] = "pending"
            s["completed_date"] = None
            s["performed_by"] = None


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
        "payment_status": _payment_status(total, received),
    }


# Values of the stored `payment_status` field:
#   paid    — received covers the system cost
#   due     — a system cost is set and part of it is still outstanding
#   no_cost — SYSTEM_COST is blank/unparseable, so "paid" can't be judged
PAYMENT_STATUSES = ("paid", "due", "no_cost")


def _payment_status(total: float, received: float) -> str:
    if total <= 0:
        return "no_cost"
    return "paid" if received >= total else "due"


def compute_payment_status(customer: dict) -> str:
    """Derived payment status, stored on the customer as `payment_status` so the
    installations overview can filter on it inside MongoDB (SYSTEM_COST is free
    text, which an aggregation pipeline can't reliably parse).

    Every write that changes SYSTEM_COST or received_payments must refresh it;
    customers saved before this field existed are backfilled at startup."""
    return payment_info(customer)["payment_status"]


class ReceivedPayment(BaseModel):
    amount: float = Field(ge=0)
    date: Optional[str] = None  # "YYYY-MM-DD"


class PaymentUpdate(BaseModel):
    received_payments: List[ReceivedPayment] = Field(default_factory=list)


class SerialsUpdate(BaseModel):
    """Inverter / panel serial numbers entered on the installation page.

    These are recorded purely as equipment data — they no longer drive the
    installation date, which is derived from the checklist's Inverter / Solar
    Panel Installation steps (see compute_installation_date).
    """
    INVERTER_SR_NO: Optional[str] = None
    PANEL_SR_NO: Optional[str] = None


def compute_serials_update(body: "SerialsUpdate") -> dict:
    """Build the $set fields for a serials update — just the cleaned values."""
    return {
        "INVERTER_SR_NO": (body.INVERTER_SR_NO or "").strip(),
        "PANEL_SR_NO": (body.PANEL_SR_NO or "").strip(),
    }
