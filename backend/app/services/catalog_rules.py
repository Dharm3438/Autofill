"""
Customer fields that must come from the admin-managed catalog (catalog_items).

The customer model checks types (a capacity is a number, ...); this module
checks the *choice*, which needs the database: the dealer / make / capacity /
watt must be an active catalog item. A customer may keep a value that has since
been hidden (deactivated) — it just can't be newly picked.

Text choices are stored with the catalog's exact spelling. Capacity and watt
are stored as numbers and matched through the catalog's text form
(3.3 → "3.3 kW", 540 → "540").
"""
import re

from fastapi import HTTPException

from ..models.catalog import CATALOG_TYPES, normalize_value, value_key
from ..models.customer import field_label

# customer field -> catalog list
CHOICE_FIELDS = {
    "DEALER_NAME": "dealer",
    "INVERTER_MAKE": "inverter_make",
    "INVERTER_CAPACITY": "inverter_capacity",
    "PANEL_COMPANY": "panel_company",
    "PANEL_WATT": "panel_watt",
}


class Catalog:
    """All catalog items, indexed by list and lower-cased value."""

    def __init__(self, docs):
        self.items: dict[str, dict] = {t: {} for t in CATALOG_TYPES}
        for d in docs:
            if d.get("type") in self.items:
                self.items[d["type"]][d.get("key") or value_key(d["value"])] = d

    @classmethod
    async def load(cls, db) -> "Catalog":
        return cls([d async for d in db.catalog_items.find({})])

    def find(self, list_type: str, value):
        """The catalog item for a stored customer value (text or number)."""
        if value is None:
            return None
        try:
            text = normalize_value(list_type, value)
        except ValueError:
            return None
        return self.items[list_type].get(value_key(text))

    def warranty_years(self, list_type: str, make):
        """'10 YEAR' on the make's catalog item → 10 (hidden makes included)."""
        item = self.find(list_type, make)
        m = re.match(r"\s*(\d+)", (item or {}).get("warranty") or "")
        return int(m.group(1)) if m else None


def _same_value(a, b) -> bool:
    """Is `a` the same stored choice as `b`? Text ignores case/spacing; numbers compare as numbers."""
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return value_key(" ".join(a.split())) == value_key(" ".join(b.split()))
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def _shown(list_type: str, value) -> str:
    """The value as the error message shows it ("3.3 kW"); falls back to the raw value."""
    if isinstance(value, str):
        return value
    try:
        return normalize_value(list_type, value)
    except ValueError:  # e.g. outside the catalog's range
        try:
            number = f"{float(value):g}"
        except (TypeError, ValueError):
            return str(value)
        return f"{number} kW" if CATALOG_TYPES[list_type]["format"] == "kw" else number


def check_choices(catalog: Catalog, data: dict, current: dict | None = None) -> dict:
    """Validate the choice fields present in `data` (in place) and return it.

    Raises 422 naming every field whose value isn't an active catalog item —
    unless it's the value the customer already has (`current`). The edit form
    sends every field back on each save, so an unchanged value is always
    accepted, even one that matches no catalog item at all (e.g. a dealer saved
    before the dealer list existed): otherwise such a customer could never be
    saved again."""
    problems = []
    for field, list_type in CHOICE_FIELDS.items():
        value = data.get(field)
        if value is None:
            continue
        if current is not None and _same_value(value, current.get(field)):
            data[field] = current[field]  # unchanged: keep exactly what's stored
            continue
        item = catalog.find(list_type, value)
        if item is None or not item.get("active", True):
            shown = _shown(list_type, value)
            problems.append(
                f"{field_label(field)} “{shown}” isn't in the {CATALOG_TYPES[list_type]['label']} list"
            )
            continue
        if isinstance(value, str):
            data[field] = item["value"]  # the catalog's exact spelling
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    return data
