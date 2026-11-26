from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

from .customer import IsoDay, Serials, Text


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
    {"key": "rts_upload", "label": "RTS Document Upload", "short": "RTS"},
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
    Null until at least one of them is marked done with a date.

    Completed dates are ISO strings (YYYY-MM-DD), so lexical max == latest.
    """
    dates = [
        s["completed_date"]
        for s in steps
        if s.get("key") in INSTALLATION_DATE_STEP_KEYS and s.get("completed_date")
    ]
    return max(dates) if dates else None


class InstallationStepUpdate(BaseModel):
    status: Optional[Literal["pending", "done"]] = None
    completed_date: IsoDay = None
    performed_by: Text = None


class InstallationGroupUpdate(BaseModel):
    """Save a whole step group at once: which members are done, plus the one
    completed date and "done by" shared by every done member."""
    done_keys: List[str] = Field(default_factory=list)
    completed_date: IsoDay = None
    performed_by: Text = None


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


# Payment status values:
#   paid    — received covers the system cost
#   due     — a system cost is set and part of it is still outstanding
#   no_cost — no system cost set, so "paid" can't be judged
PAYMENT_STATUSES = ("paid", "due", "no_cost")


def payment_info(customer: dict) -> dict:
    """Total / received / remaining for one customer.

    Total is SYSTEM_COST (whole rupees, set on the customer form). Received is
    the sum of the dated received-payment entries. Nothing here is stored: the
    installations overview computes the same values inside MongoDB with
    PAYMENT_EXPRESSIONS below, so the two must stay in step (see tests).
    """
    total = customer.get("SYSTEM_COST") or 0
    entries = customer.get("received_payments") or []
    received = sum(e.get("amount") or 0 for e in entries)
    if total <= 0:
        status = "no_cost"
    else:
        status = "paid" if received >= total else "due"
    return {
        "total_payment": total,
        "received_payment": received,
        "remaining_payment": max(total - received, 0),
        # Share of the cost received, 0–100 (overpayment capped at 100).
        "paid_percent": min(received / total * 100, 100.0) if total > 0 else 0.0,
        "received_payments": entries,
        "payment_status": status,
    }


# The same calculations as MongoDB aggregation expressions, applied in two
# $addFields stages (the second uses the first's results).
_TOTAL = {"$ifNull": ["$SYSTEM_COST", 0]}
PAYMENT_EXPRESSIONS = (
    {
        # Sum of every entry's amount (missing list or amounts count as 0).
        "_received": {"$sum": "$received_payments.amount"},
    },
    {
        "paid_percent": {"$cond": [
            {"$gt": [_TOTAL, 0]},
            {"$min": [100, {"$multiply": [{"$divide": ["$_received", _TOTAL]}, 100]}]},
            0,
        ]},
        "payment_status": {"$switch": {
            "branches": [
                {"case": {"$lte": [_TOTAL, 0]}, "then": "no_cost"},
                {"case": {"$gte": ["$_received", _TOTAL]}, "then": "paid"},
            ],
            "default": "due",
        }},
    },
)


class ReceivedPayment(BaseModel):
    amount: int = Field(ge=0)  # whole rupees
    date: IsoDay = None


class PaymentUpdate(BaseModel):
    received_payments: List[ReceivedPayment] = Field(default_factory=list)


class SerialsUpdate(BaseModel):
    """Inverter serial number(s) entered on the installation page.

    Recorded purely as equipment data — it does not drive the installation
    date, which is derived from the checklist's Inverter / Solar Panel
    Installation steps (see compute_installation_date).
    """
    INVERTER_SR_NO: Serials = None


def compute_serials_update(body: "SerialsUpdate") -> dict:
    """Build the $set fields for a serials update (comma-separated, cleaned)."""
    return {"INVERTER_SR_NO": body.INVERTER_SR_NO}
