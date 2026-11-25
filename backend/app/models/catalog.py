"""Admin-managed option lists for the customer form ("catalog").

Dealers and equipment (inverter makes/capacities, panel companies/watts,
generation meter makes) used to be hard-coded in the frontend. They now live in
the `catalog_items` collection, one document per option:

    { type, value, key, warranty?, active, created_by, created_at, updated_at }

  • `value` is what gets copied onto a customer (DEALER_NAME, INVERTER_MAKE …)
    and printed on documents. Customers store the text itself, not a reference,
    so options are never renamed or deleted — only deactivated (`active=False`),
    which hides them from new selections while old customers keep their value.
  • `key` is the lower-cased value; a unique (type, key) index blocks
    "Polycab" / "polycab" duplicates.
  • `warranty` exists only on makes (inverter / panel) and auto-fills the
    customer's guarantee field when that make is picked.

Values are normalised to one format ("7 kW", "550") because the inventory panel
groups stock by the exact text — "7kw" and "7 kW" would otherwise split into
two stock lines.
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel

CatalogType = Literal[
    "dealer",
    "inverter_make",
    "inverter_capacity",
    "panel_company",
    "panel_watt",
]

# Order here is the tab order in the admin screen.
CATALOG_TYPES: dict[str, dict] = {
    "dealer":                {"label": "Dealers",                "format": "text", "warranty": False},
    "inverter_make":         {"label": "Inverter Makes",         "format": "text", "warranty": True},
    "inverter_capacity":     {"label": "Inverter Capacities",    "format": "kw",   "warranty": False},
    "panel_company":         {"label": "Panel Companies",        "format": "text", "warranty": True},
    "panel_watt":            {"label": "Panel Watts",            "format": "watt", "warranty": False},
}

# Seeded the first time a list is empty (these were the hard-coded frontend
# lists).
DEFAULTS: dict[str, list] = {
    "dealer": [
        "Devicharan Katkar", "Sadguru electronic", "Pravin Ranalkar",
        "Rajesh Khona Pachora", "Somnath Chaudhary", "Santosh Gadia",
        "Nilkanth Salunkhe", "Adiwal Pachora", "Balasaheb Karmad",
        "Satish Khairnar Bhoras", "Sudhir kumbhar", "Sagar Rajput", "Office",
    ],
    "inverter_make": [
        ("UTL", "10 YEAR"), ("WAAREE", "10 YEAR"), ("APS", "10 YEAR"),
        ("KSOLARE", "10 YEAR"), ("GOODWE", "10 YEAR"), ("Xwatt", "10 YEAR"),
        ("Polycab", "8 YEAR"), ("Microtek Inverter", "10 YEAR"),
        ("Pv blink", "10 YEAR"),
    ],
    "inverter_capacity": [
        "1 kW", "2 kW", "3 kW", "3.3 kW", "3.6 kW", "4 kW", "4.6 kW",
        "5 kW", "5.5 kW", "6 kW", "8 kW", "10 kW", "12 kW", "15 kW", "20 kW",
    ],
    "panel_company": [
        ("UTL", "27 YEAR"), ("ADANI", "30 YEAR"), ("WAAREE", "30 YEAR"),
        ("TATA", "30 YEAR"), ("PREMIER", "30 YEAR"), ("APS", "30 YEAR"),
    ],
    "panel_watt": [
        "500", "525", "530", "540", "545", "550", "570", "575", "580",
        "585", "590", "600", "610", "615", "620",
    ],
}

_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*$")


def _fmt_number(n: float) -> str:
    """3.30 → '3.3', 7.0 → '7'."""
    return f"{n:.3f}".rstrip("0").rstrip(".")


def normalize_value(type_: str, raw) -> str:
    """Clean an option value into its canonical form. Raises ValueError."""
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not text:
        raise ValueError("Enter a value")
    if len(text) > 80:
        raise ValueError("Keep it under 80 characters")
    fmt = CATALOG_TYPES[type_]["format"]
    if fmt == "text":
        return text
    m = _NUMBER.match(text)
    unit = (m.group(2).lower() if m else "")
    if fmt == "kw":
        if not m or unit not in ("", "kw"):
            raise ValueError("Enter the capacity in kW, e.g. 7 or 3.3")
        n = float(m.group(1))
        if not 0 < n <= 1000:
            raise ValueError("Capacity must be between 0 and 1000 kW")
        return f"{_fmt_number(n)} kW"
    if fmt == "watt":
        if not m or unit not in ("", "w", "wp"):
            raise ValueError("Enter the panel watt as a number, e.g. 550")
        n = float(m.group(1))
        if not 0 < n <= 5000:
            raise ValueError("Panel watt must be between 0 and 5000")
        return _fmt_number(n)
    return text


def normalize_warranty(raw) -> str:
    """'10', '10 years', '10 YEAR' → '10 YEAR' (the format templates print)."""
    m = re.match(r"^\s*(\d{1,3})\s*(?:y|yr|yrs|year|years)?\s*$", str(raw or ""), re.I)
    if not m or int(m.group(1)) == 0:
        raise ValueError("Enter the warranty in years, e.g. 10")
    return f"{int(m.group(1))} YEAR"


def value_key(value: str) -> str:
    return value.lower()


def sort_key(type_: str, value: str):
    """Numeric lists sort by number; text lists alphabetically."""
    if CATALOG_TYPES[type_]["format"] in ("kw", "watt"):
        m = _NUMBER.match(value)
        return (0, float(m.group(1)) if m else 0.0, value)
    return (0, 0.0, value.lower())


def item_to_out(doc: dict) -> dict:
    out = {
        "id": str(doc["_id"]),
        "type": doc["type"],
        "value": doc["value"],
        "active": doc.get("active", True),
    }
    if CATALOG_TYPES.get(doc["type"], {}).get("warranty"):
        out["warranty"] = doc.get("warranty") or ""
    return out


class CatalogItemCreate(BaseModel):
    type: CatalogType
    value: str
    warranty: Optional[str] = None


class CatalogItemUpdate(BaseModel):
    warranty: Optional[str] = None
    active: Optional[bool] = None
