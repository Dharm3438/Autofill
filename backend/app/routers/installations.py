from fastapi import APIRouter, HTTPException, Depends, Query, status
from ..core.database import get_db
from ..core.deps import get_current_user
from .customers import search_or
from ..models.installation import (
    INSTALLATION_STEPS,
    STEP_KEYS,
    merge_steps,
    compute_overall_status,
    payment_info,
    InstallationStepUpdate,
    PaymentUpdate,
)
from bson import ObjectId
from datetime import datetime, timezone, date

router = APIRouter(prefix="/installations", tags=["installations"])


def _storable(steps: list) -> list:
    """Drop the derived `label` field before persisting — labels live in code."""
    return [
        {k: s[k] for k in ("key", "status", "completed_date", "performed_by", "notes")}
        for s in steps
    ]


def _summarize(steps: list) -> dict:
    done_count = sum(1 for s in steps if s.get("status") == "done")
    return {
        "steps": steps,
        "done_count": done_count,
        "total": len(steps),
        "overall_status": compute_overall_status(steps),
    }


# Fields read to build a customer row in the overview list. Projecting to just
# these (instead of fetching the full ~30-column document) cuts how much each
# customer transfers from MongoDB. payment_info needs SYSTEM_COST /
# received_payments / received_payment; _summarize needs installation_steps.
_OVERVIEW_ROW_FIELDS = {
    "CONSUMER_NAME": 1, "DEALER_NAME": 1, "CONSUMER_NO": 1, "CONSUMER_PHONE": 1,
    "INSTALLATION_CITY": 1, "INVERTER_MAKE": 1, "INVERTER_CAPACITY": 1,
    "PANEL_COMPANY": 1, "PANEL_WATT": 1, "NO_OF_PANEL": 1,
    "installation_steps": 1, "SYSTEM_COST": 1,
    "received_payments": 1, "received_payment": 1, "created_at": 1,
}
# The summary only needs each customer's steps — nothing else.
_OVERVIEW_SUMMARY_FIELDS = {"installation_steps": 1}


@router.get("/overview")
async def installations_overview(
    search: str = Query(default=""),
    status: str = Query(default=""),          # not_started | in_progress | completed
    pending_step: str = Query(default=""),    # a step key still pending
    dealer: str = Query(default=""),          # exact dealer name to filter by
    summary_only: bool = Query(default=False),  # dashboard: skip the customer list
    _=Depends(get_current_user),
):
    db = get_db()
    query = {}
    if search:
        query["$or"] = search_or(search)
    if dealer:
        query["DEALER_NAME"] = dealer

    customers = []
    summary = {
        "total_customers": 0,
        "completed": 0,
        "in_progress": 0,
        "not_started": 0,
        "per_step_pending": {s["key"]: 0 for s in INSTALLATION_STEPS},
    }

    # The dashboard only renders `summary`, so it sends summary_only=1 and we
    # fetch just installation_steps and never build/serialize the row list.
    projection = _OVERVIEW_SUMMARY_FIELDS if summary_only else _OVERVIEW_ROW_FIELDS
    cursor = db.customers.find(query, projection).sort("created_at", -1)
    async for c in cursor:
        steps = merge_steps(c.get("installation_steps"))
        info = _summarize(steps)

        # Summary counts reflect ALL matching customers (before status/step filters)
        # so the dashboard totals stay meaningful.
        summary["total_customers"] += 1
        summary[info["overall_status"]] += 1
        for s in steps:
            if s.get("status") != "done":
                summary["per_step_pending"][s["key"]] += 1

        if summary_only:
            continue
        if status and info["overall_status"] != status:
            continue
        if pending_step:
            still_pending = any(
                s["key"] == pending_step and s.get("status") != "done" for s in steps
            )
            if not still_pending:
                continue

        customers.append(
            {
                "id": str(c["_id"]),
                "CONSUMER_NAME": c.get("CONSUMER_NAME"),
                "DEALER_NAME": c.get("DEALER_NAME"),
                "CONSUMER_NO": c.get("CONSUMER_NO"),
                "CONSUMER_PHONE": c.get("CONSUMER_PHONE"),
                "INSTALLATION_CITY": c.get("INSTALLATION_CITY"),
                "INVERTER_MAKE": c.get("INVERTER_MAKE"),
                "INVERTER_CAPACITY": c.get("INVERTER_CAPACITY"),
                "PANEL_COMPANY": c.get("PANEL_COMPANY"),
                "PANEL_WATT": c.get("PANEL_WATT"),
                "NO_OF_PANEL": c.get("NO_OF_PANEL"),
                **info,
                **payment_info(c),
            }
        )

    return {
        "success": True,
        "data": customers,
        "summary": summary,
        "steps": INSTALLATION_STEPS,
    }


@router.get("/{customer_id}")
async def get_installation(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    c = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    steps = merge_steps(c.get("installation_steps"))
    return {
        "success": True,
        "data": {
            "customer_id": customer_id,
            "CONSUMER_NAME": c.get("CONSUMER_NAME"),
            **_summarize(steps),
            **payment_info(c),
        },
    }


@router.put("/{customer_id}/payment")
async def update_installation_payment(
    customer_id: str,
    body: PaymentUpdate,
    _=Depends(get_current_user),
):
    db = get_db()
    c = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Persist the full list of dated received-payment entries; the total is
    # derived from SYSTEM_COST and is never written here.
    entries = [p.model_dump() for p in body.received_payments]
    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {
            "$set": {
                "received_payments": entries,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            # Drop the obsolete single-value field if it lingers from old records.
            "$unset": {"received_payment": "", "total_payment": ""},
        },
    )

    merged = {**c, "received_payments": entries}
    merged.pop("received_payment", None)
    return {
        "success": True,
        "data": {"customer_id": customer_id, **payment_info(merged)},
    }


@router.put("/{customer_id}/steps/{step_key}")
async def update_installation_step(
    customer_id: str,
    step_key: str,
    body: InstallationStepUpdate,
    _=Depends(get_current_user),
):
    if step_key not in STEP_KEYS:
        raise HTTPException(status_code=400, detail="Unknown installation step")

    db = get_db()
    c = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    steps = merge_steps(c.get("installation_steps"))
    target = next(s for s in steps if s["key"] == step_key)

    new_status = body.status if body.status is not None else target["status"]
    if new_status == "done":
        target["status"] = "done"
        # Default to today when marked done without an explicit date.
        target["completed_date"] = (
            body.completed_date
            if body.completed_date is not None
            else (target["completed_date"] or date.today().isoformat())
        )
        if body.performed_by is not None:
            target["performed_by"] = body.performed_by
        if body.notes is not None:
            target["notes"] = body.notes
    else:
        # Toggling back to pending clears the recorded details.
        target["status"] = "pending"
        target["completed_date"] = None
        target["performed_by"] = None
        target["notes"] = body.notes if body.notes is not None else None

    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {
            "$set": {
                "installation_steps": _storable(steps),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    return {
        "success": True,
        "data": {"customer_id": customer_id, **_summarize(steps)},
    }
