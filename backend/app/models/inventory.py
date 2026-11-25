"""Inventory tracking for installation equipment.

Two quantities are surfaced per equipment combination on the installation page:

  • required  — pending demand: units needed by customers whose matching
                installation step is NOT yet done.
  • in_stock  — units physically on hand right now = the base stock you
                entered minus what's already been consumed by customers whose
                matching step IS done. So completing a customer's panel or
                inverter step automatically deducts from available stock.

Only solar panels and inverters are tracked.

Base stock lives in the `inventory` collection, one doc per (category, company,
spec) key. Everything else (required / consumed / in_stock / shortfall) is
derived on the fly from customer records, so the numbers can never drift out of
sync with the installation checklist.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal

# The equipment categories we track, and the installation step whose completion
# marks a unit as "consumed" (removed from available stock).
CATEGORY_STEP = {
    "panel": "panels",
    "inverter": "inverter",
}
CATEGORIES = tuple(CATEGORY_STEP.keys())

CATEGORY_LABEL = {
    "panel": "Solar Panels",
    "inverter": "Inverters",
}


def _clean(v) -> str:
    return str(v).strip() if v is not None else ""


def line_label(category: str, company: str, spec: str) -> str:
    """Human-readable name for an inventory line (e.g. 'UTL · 550 W')."""
    if category == "panel":
        parts = [company or "Unspecified"]
        if spec:
            parts.append(f"{spec} W")
        return " · ".join(parts)
    if category == "inverter":
        parts = [company or "Unspecified"]
        if spec:
            parts.append(spec)
        return " · ".join(parts)
    return company or "Unspecified"


def stock_key(category: str, company: str, spec: str) -> dict:
    """The query/identity for a stock document."""
    return {
        "category": category,
        "company": _clean(company),
        "spec": _clean(spec),
    }


class StockUpdate(BaseModel):
    """Set the base (on-hand) stock quantity for one equipment combination."""
    category: Literal["panel", "inverter"]
    company: str = ""
    spec: str = ""
    stock: int = Field(ge=0)
