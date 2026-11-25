import asyncio
import re
from fastapi import APIRouter, HTTPException, Depends, Query, status
from ..core.database import get_db
from ..core.permissions import P, require, parse_object_id
from ..models.installation import (
    INSTALLATION_STEPS,
    STEP_KEYS,
    GROUP_KEYS,
    apply_group_update,
    merge_steps,
    compute_overall_status,
    compute_installation_date,
    payment_info,
    compute_payment_status,
    PAYMENT_STATUSES,
    compute_serials_update,
    InstallationStepUpdate,
    InstallationGroupUpdate,
    PaymentUpdate,
    SerialsUpdate,
)
from bson import ObjectId
from datetime import datetime, timezone, date

router = APIRouter(prefix="/installations", tags=["installations"])


def _storable(steps: list) -> list:
    """Drop derived fields (label, group, ...) before persisting — they live in code."""
    return [
        {k: s[k] for k in ("key", "status", "completed_date", "performed_by")}
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


# Fields the overview rows need. Projecting down to these before sorting keeps
# the in-memory sort small even with thousands of customers.
_OVERVIEW_FIELDS = (
    "CONSUMER_NAME", "DEALER_NAME", "CONSUMER_NO", "CONSUMER_PHONE",
    "INSTALLATION_CITY", "INVERTER_MAKE", "INVERTER_CAPACITY",
    "PANEL_COMPANY", "PANEL_WATT", "NO_OF_PANEL",
    "installation_steps", "SYSTEM_COST", "received_payments", "received_payment",
    "payment_status",
)

_STEP_KEY_LIST = [s["key"] for s in INSTALLATION_STEPS]
_TOTAL_STEPS = len(_STEP_KEY_LIST)

OVERVIEW_PAGE_SIZE_MAX = 100


def _overview_base_pipeline(query: dict) -> list:
    """Match customers and derive, inside MongoDB, the same progress fields
    `merge_steps` + `_summarize` compute in Python, so the database can filter,
    sort and page on them:

      _done_keys   — distinct current step keys marked done (unknown keys and
                     missing/non-list `installation_steps` are ignored, like merge_steps)
      _done_count  — len(_done_keys)
      _status      — not_started / in_progress / completed
      _name_sort   — lower-cased name, for a case-insensitive A→Z tiebreak
    """
    stored_done_keys = {
        "$map": {
            "input": {
                "$filter": {
                    "input": {"$cond": [{"$isArray": "$installation_steps"}, "$installation_steps", []]},
                    "as": "s",
                    "cond": {"$eq": ["$$s.status", "done"]},
                }
            },
            "as": "s",
            "in": "$$s.key",
        }
    }
    # Walk the canonical step list (not the stored one) so duplicates and
    # removed/unknown keys can't inflate the count.
    done_keys = {
        "$filter": {
            "input": {"$literal": _STEP_KEY_LIST},
            "as": "k",
            "cond": {"$in": ["$$k", stored_done_keys]},
        }
    }
    return [
        {"$match": query},
        {"$project": {**{f: 1 for f in _OVERVIEW_FIELDS}, "_done_keys": done_keys}},
        {"$addFields": {
            "_done_count": {"$size": "$_done_keys"},
            "_name_sort": {"$toLower": {"$ifNull": ["$CONSUMER_NAME", ""]}},
        }},
        {"$addFields": {
            "_status": {
                "$switch": {
                    "branches": [
                        {"case": {"$eq": ["$_done_count", 0]}, "then": "not_started"},
                        {"case": {"$gte": ["$_done_count", _TOTAL_STEPS]}, "then": "completed"},
                    ],
                    "default": "in_progress",
                }
            }
        }},
    ]


def _overview_summary_stage() -> dict:
    """One $group producing the dashboard counts in a single small document."""
    group = {
        "_id": None,
        "total_customers": {"$sum": 1},
        **{
            st: {"$sum": {"$cond": [{"$eq": ["$_status", st]}, 1, 0]}}
            for st in ("completed", "in_progress", "not_started")
        },
    }
    for i, key in enumerate(_STEP_KEY_LIST):
        # Field names can't contain the raw key safely in every case; index them.
        group[f"done_{i}"] = {"$sum": {"$cond": [{"$in": [key, "$_done_keys"]}, 1, 0]}}
    return {"$group": group}


def _summary_from_group(doc: dict | None) -> dict:
    doc = doc or {}
    total = doc.get("total_customers", 0)
    return {
        "total_customers": total,
        "completed": doc.get("completed", 0),
        "in_progress": doc.get("in_progress", 0),
        "not_started": doc.get("not_started", 0),
        "per_step_pending": {
            key: total - doc.get(f"done_{i}", 0) for i, key in enumerate(_STEP_KEY_LIST)
        },
    }


def _overview_row(c: dict) -> dict:
    steps = merge_steps(c.get("installation_steps"))
    return {
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
        **_summarize(steps),
        **payment_info(c),
    }


@router.get("/overview")
async def installations_overview(
    search: str = Query(default=""),
    status: str = Query(default=""),          # not_started | in_progress | completed
    pending_step: str = Query(default=""),    # a step key still pending
    done_step: str = Query(default=""),       # a step key already done
    payment: str = Query(default=""),         # paid | due | no_cost
    dealer: str = Query(default=""),          # exact dealer name to filter by
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=OVERVIEW_PAGE_SIZE_MAX),
    # Print needs every filtered row; it asks for them explicitly, on demand.
    fetch_all: bool = Query(default=False, alias="all"),
    _=Depends(require(P.INSTALLATIONS_READ)),
):
    """
    One page of installation progress, sorted by completion (most done first)
    then name. Filtering, sorting and paging happen in MongoDB, so only the
    requested page leaves the database.

    `summary` counts ALL customers matching search/dealer (before the status,
    step and payment filters) so the dashboard totals stay meaningful.
    `total` is the number of rows after every filter, for the pager.
    """
    db = get_db()
    query = {}
    if search:
        query["$or"] = [
            {"CONSUMER_NAME": {"$regex": re.escape(search), "$options": "i"}},
            {"CONSUMER_APP_NO": {"$regex": re.escape(search), "$options": "i"}},
            {"SUBSIDY_APP_NO": {"$regex": re.escape(search), "$options": "i"}},
            {"CONSUMER_PHONE": {"$regex": re.escape(search), "$options": "i"}},
        ]
    if dealer:
        query["DEALER_NAME"] = dealer

    base = _overview_base_pipeline(query)

    row_filter = {}
    match_nothing = False
    if status:
        row_filter["_status"] = status
    # Both step filters constrain _done_keys, so combine them with $and.
    step_conds = []
    if pending_step:
        if pending_step in STEP_KEYS:
            step_conds.append({"_done_keys": {"$ne": pending_step}})
        else:
            # An unknown step can never be pending — match nothing, as before.
            match_nothing = True
    if done_step:
        if done_step in STEP_KEYS:
            step_conds.append({"_done_keys": done_step})
        else:
            match_nothing = True
    if step_conds:
        row_filter["$and"] = step_conds
    if payment:
        if payment in PAYMENT_STATUSES:
            row_filter["payment_status"] = payment
        else:
            match_nothing = True
    if match_nothing:
        row_filter = {"_id": {"$exists": False}}
    filtered = base + ([{"$match": row_filter}] if row_filter else [])

    rows_pipeline = filtered + [{"$sort": {"_done_count": -1, "_name_sort": 1, "_id": 1}}]
    if not fetch_all:
        rows_pipeline += [{"$skip": (page - 1) * limit}, {"$limit": limit}]

    summary_docs, count_docs, raw_rows = await asyncio.gather(
        db.customers.aggregate(base + [_overview_summary_stage()]).to_list(length=1),
        db.customers.aggregate(filtered + [{"$count": "n"}]).to_list(length=1),
        db.customers.aggregate(rows_pipeline).to_list(length=None),
    )

    return {
        "success": True,
        "data": [_overview_row(c) for c in raw_rows],
        "total": count_docs[0]["n"] if count_docs else 0,
        "page": 1 if fetch_all else page,
        "limit": None if fetch_all else limit,
        "summary": _summary_from_group(summary_docs[0] if summary_docs else None),
        "steps": INSTALLATION_STEPS,
    }


@router.get("/{customer_id}")
async def get_installation(customer_id: str, _=Depends(require(P.INSTALLATIONS_READ))):
    db = get_db()
    c = await db.customers.find_one({"_id": parse_object_id(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    steps = merge_steps(c.get("installation_steps"))
    return {
        "success": True,
        "data": {
            "customer_id": customer_id,
            "CONSUMER_NAME": c.get("CONSUMER_NAME"),
            "INVERTER_SR_NO": c.get("INVERTER_SR_NO") or "",
            "PANEL_SR_NO": c.get("PANEL_SR_NO") or "",
            "INSTALLATION_DATE": c.get("INSTALLATION_DATE") or "",
            **_summarize(steps),
            **payment_info(c),
        },
    }


@router.put("/{customer_id}/serials")
async def update_installation_serials(
    customer_id: str,
    body: SerialsUpdate,
    _=Depends(require(P.INSTALLATIONS_WRITE)),
):
    """Save the inverter / panel serial numbers entered after installation.

    These are recorded as equipment data only. The installation date is no
    longer derived here — it comes from the checklist's Inverter / Solar Panel
    Installation completion dates (see update_installation_step)."""
    db = get_db()
    c = await db.customers.find_one({"_id": parse_object_id(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    fields = compute_serials_update(body)
    await db.customers.update_one(
        {"_id": parse_object_id(customer_id)},
        {
            "$set": {
                **fields,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            # Drop the obsolete set-date fields from the old serial-driven logic.
            "$unset": {"inverter_sr_set_date": "", "panel_sr_set_date": ""},
        },
    )

    return {
        "success": True,
        "data": {
            "customer_id": customer_id,
            "INVERTER_SR_NO": fields["INVERTER_SR_NO"],
            "PANEL_SR_NO": fields["PANEL_SR_NO"],
        },
    }


@router.put("/{customer_id}/payment")
async def update_installation_payment(
    customer_id: str,
    body: PaymentUpdate,
    _=Depends(require(P.INSTALLATIONS_WRITE)),
):
    db = get_db()
    c = await db.customers.find_one({"_id": parse_object_id(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Persist the full list of dated received-payment entries; the total is
    # derived from SYSTEM_COST and is never written here.
    entries = [p.model_dump() for p in body.received_payments]
    merged = {**c, "received_payments": entries}
    merged.pop("received_payment", None)
    await db.customers.update_one(
        {"_id": parse_object_id(customer_id)},
        {
            "$set": {
                "received_payments": entries,
                "payment_status": compute_payment_status(merged),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            # Drop the obsolete single-value field if it lingers from old records.
            "$unset": {"received_payment": "", "total_payment": ""},
        },
    )

    return {
        "success": True,
        "data": {"customer_id": customer_id, **payment_info(merged)},
    }


@router.put("/{customer_id}/steps/{step_key}")
async def update_installation_step(
    customer_id: str,
    step_key: str,
    body: InstallationStepUpdate,
    _=Depends(require(P.INSTALLATIONS_WRITE)),
):
    if step_key not in STEP_KEYS:
        raise HTTPException(status_code=400, detail="Unknown installation step")

    db = get_db()
    c = await db.customers.find_one({"_id": parse_object_id(customer_id)})
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
        # Grouped steps share one date and person: keep the group's other done
        # members in sync with this one.
        if target.get("group"):
            for s in steps:
                if s is not target and s.get("group") == target["group"] and s["status"] == "done":
                    s["completed_date"] = target["completed_date"]
                    s["performed_by"] = target["performed_by"]
    else:
        # Toggling back to pending clears the recorded details.
        target["status"] = "pending"
        target["completed_date"] = None
        target["performed_by"] = None

    return await _save_steps(db, customer_id, steps)


@router.put("/{customer_id}/groups/{group_key}")
async def update_installation_group(
    customer_id: str,
    group_key: str,
    body: InstallationGroupUpdate,
    _=Depends(require(P.INSTALLATIONS_WRITE)),
):
    """Save a step group (e.g. wiring) in one go: per-member done/pending, with a
    single completed date and "done by" shared by all done members."""
    if group_key not in GROUP_KEYS:
        raise HTTPException(status_code=400, detail="Unknown installation step group")

    db = get_db()
    c = await db.customers.find_one({"_id": parse_object_id(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    steps = merge_steps(c.get("installation_steps"))
    apply_group_update(steps, group_key, body)
    return await _save_steps(db, customer_id, steps)


async def _save_steps(db, customer_id: str, steps: list) -> dict:
    """Persist merged steps (and the derived INSTALLATION_DATE); return the response."""
    # INSTALLATION_DATE tracks the Inverter / Solar Panel Installation steps:
    # the later of their two completion dates (or whichever is present).
    installation_date = compute_installation_date(steps)
    await db.customers.update_one(
        {"_id": parse_object_id(customer_id)},
        {
            "$set": {
                "installation_steps": _storable(steps),
                "INSTALLATION_DATE": installation_date,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    return {
        "success": True,
        "data": {
            "customer_id": customer_id,
            "INSTALLATION_DATE": installation_date,
            **_summarize(steps),
        },
    }
