from fastapi import APIRouter, Depends
from datetime import datetime, timezone

from ..core.database import get_db
from ..core.permissions import P, require
from ..models.installation import merge_steps
from ..services.formatting import fmt_number
from ..models.inventory import (
    CATEGORIES,
    CATEGORY_STEP,
    CATEGORY_LABEL,
    StockUpdate,
    line_label,
    stock_key,
    _clean,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _demand_lines(customer: dict, step_done: dict) -> list:
    """Yield (category, company, spec, qty, done) tuples for one customer.

    Every customer in the system is an upcoming/ongoing install, so each one
    needs a generation meter and a net meter. Panels and inverters are only
    counted once their combination is specified (otherwise there's nothing to
    attribute the demand to). `done` reflects that category's install step
    (step_done is keyed by category, not step key).
    """
    lines = []

    # Panels — grouped by company + watt, quantity = number of panels.
    # Specs are the stored numbers printed plainly (540, 3.3) — the same text
    # the inventory form sends for a stock line.
    panel_qty = customer.get("NO_OF_PANEL") or 0
    if panel_qty and _clean(customer.get("PANEL_COMPANY")):
        lines.append((
            "panel",
            _clean(customer.get("PANEL_COMPANY")),
            fmt_number(customer.get("PANEL_WATT")),
            panel_qty,
            step_done["panel"],
        ))

    # Inverter — one per customer, grouped by make + capacity.
    if _clean(customer.get("INVERTER_MAKE")):
        lines.append((
            "inverter",
            _clean(customer.get("INVERTER_MAKE")),
            fmt_number(customer.get("INVERTER_CAPACITY")),
            1,
            step_done["inverter"],
        ))

    # Generation meter — one per customer, grouped by make.
    lines.append((
        "generation_meter",
        _clean(customer.get("GENERATION_METER_MAKE")),
        "",
        1,
        step_done["generation_meter"],
    ))

    # Net meter — one per customer, single generic line (no make field).
    lines.append((
        "net_meter",
        "",
        "",
        1,
        step_done["net_meter"],
    ))

    return lines


@router.get("/overview")
async def inventory_overview(_=Depends(require(P.INSTALLATIONS_READ))):
    """Aggregate required vs. available stock for every equipment combination."""
    db = get_db()

    # Accumulate demand keyed by (category, company, spec).
    agg: dict = {}

    def bucket(category, company, spec):
        key = (category, _clean(company), _clean(spec))
        if key not in agg:
            agg[key] = {"required": 0, "consumed": 0, "base_stock": 0}
        return agg[key]

    cursor = db.customers.find(
        {},
        {
            "NO_OF_PANEL": 1, "PANEL_COMPANY": 1, "PANEL_WATT": 1,
            "INVERTER_MAKE": 1, "INVERTER_CAPACITY": 1,
            "GENERATION_METER_MAKE": 1, "installation_steps": 1,
        },
    )
    async for c in cursor:
        steps = merge_steps(c.get("installation_steps"))
        status_by_key = {s["key"]: s.get("status") for s in steps}
        step_done = {
            cat: status_by_key.get(step) == "done"
            for cat, step in CATEGORY_STEP.items()
        }
        for category, company, spec, qty, done in _demand_lines(c, step_done):
            b = bucket(category, company, spec)
            if done:
                b["consumed"] += qty
            else:
                b["required"] += qty

    # Fold in the base stock the user has entered (may include combinations with
    # no current demand — e.g. pre-stocked items).
    async for doc in db.inventory.find({}):
        b = bucket(doc.get("category"), doc.get("company"), doc.get("spec"))
        b["base_stock"] = int(doc.get("stock") or 0)

    # Shape into per-category lists.
    grouped = {cat: [] for cat in CATEGORIES}
    for (category, company, spec), v in agg.items():
        if category not in grouped:
            continue
        in_stock = v["base_stock"] - v["consumed"]
        grouped[category].append({
            "category": category,
            "company": company,
            "spec": spec,
            "label": line_label(category, company, spec),
            "required": v["required"],
            "consumed": v["consumed"],
            "base_stock": v["base_stock"],
            "in_stock": in_stock,
            "shortfall": max(v["required"] - in_stock, 0),
        })

    # Sort each category by need: most-required first so the admin sees which
    # items are in highest demand at a glance. Ties break by shortfall (the
    # more short, the higher) and then by name for a stable order.
    for cat in grouped:
        grouped[cat].sort(
            key=lambda r: (-r["required"], -r["shortfall"], r["label"].lower())
        )

    categories = [
        {"key": cat, "label": CATEGORY_LABEL[cat], "items": grouped[cat]}
        for cat in CATEGORIES
    ]
    totals = {
        cat: {
            "required": sum(r["required"] for r in grouped[cat]),
            "in_stock": sum(r["in_stock"] for r in grouped[cat]),
            "shortfall": sum(r["shortfall"] for r in grouped[cat]),
        }
        for cat in CATEGORIES
    }

    return {"success": True, "data": {"categories": categories, "totals": totals}}


@router.put("/stock")
async def set_stock(body: StockUpdate, _=Depends(require(P.INSTALLATIONS_WRITE))):
    """Upsert the base on-hand stock for one equipment combination."""
    db = get_db()
    key = stock_key(body.category, body.company, body.spec)
    await db.inventory.update_one(
        key,
        {
            "$set": {
                **key,
                "stock": body.stock,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True, "data": {**key, "stock": body.stock}}
