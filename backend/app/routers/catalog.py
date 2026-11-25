"""Dealer & equipment option lists. Everyone who fills the customer form or
works the installations page can read them; only admins can change them."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from ..core.database import get_db
from ..core.permissions import P, parse_object_id, require
from ..models.catalog import (
    CATALOG_TYPES,
    CatalogItemCreate,
    CatalogItemUpdate,
    item_to_out,
    normalize_value,
    normalize_warranty,
    sort_key,
    value_key,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

_READERS = (
    P.CUSTOMERS_CREATE,
    P.CUSTOMERS_UPDATE,
    P.INSTALLATIONS_READ,
    P.CATALOG_MANAGE,
)


def _bad(e: ValueError):
    return HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_catalog(_=Depends(require(*_READERS, any_of=True))):
    """All option lists, including inactive items (flagged `active: false`) so
    the UI can still show a deactivated value that an old customer carries."""
    db = get_db()
    items: dict[str, list] = {t: [] for t in CATALOG_TYPES}
    async for doc in db.catalog_items.find({}):
        if doc.get("type") in items:
            items[doc["type"]].append(item_to_out(doc))
    for t, rows in items.items():
        rows.sort(key=lambda r: sort_key(t, r["value"]))
    types = [
        {"key": k, "label": v["label"], "format": v["format"], "has_warranty": v["warranty"]}
        for k, v in CATALOG_TYPES.items()
    ]
    return {"success": True, "data": {"types": types, "items": items}}


@router.post("")
async def add_catalog_item(body: CatalogItemCreate, user=Depends(require(P.CATALOG_MANAGE))):
    db = get_db()
    try:
        value = normalize_value(body.type, body.value)
        warranty = normalize_warranty(body.warranty) if CATALOG_TYPES[body.type]["warranty"] else None
    except ValueError as e:
        raise _bad(e)

    label = CATALOG_TYPES[body.type]["label"].lower()
    existing = await db.catalog_items.find_one({"type": body.type, "key": value_key(value)})
    if existing:
        if existing.get("active", True):
            raise HTTPException(status_code=409, detail=f"“{existing['value']}” is already in {label}")
        raise HTTPException(
            status_code=409,
            detail=f"“{existing['value']}” is already in {label} but hidden — switch it back on in the list",
        )

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "type": body.type,
        "value": value,
        "key": value_key(value),
        "active": True,
        "created_by": str(user["_id"]),
        "created_at": now,
        "updated_at": now,
    }
    if warranty:
        doc["warranty"] = warranty
    try:
        res = await db.catalog_items.insert_one(doc)
    except DuplicateKeyError:  # lost a race with an identical add
        raise HTTPException(status_code=409, detail=f"“{value}” is already in {label}")
    doc["_id"] = res.inserted_id
    return {"success": True, "data": item_to_out(doc), "message": f"Added {value}"}


@router.put("/{item_id}")
async def update_catalog_item(
    item_id: str,
    body: CatalogItemUpdate,
    _=Depends(require(P.CATALOG_MANAGE)),
):
    """Change an item's warranty or switch it on/off. Values can't be renamed:
    customers store the text itself, so a rename would orphan their value."""
    db = get_db()
    oid = parse_object_id(item_id)
    doc = await db.catalog_items.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    update: dict = {}
    if body.warranty is not None:
        if not CATALOG_TYPES.get(doc["type"], {}).get("warranty"):
            raise HTTPException(status_code=400, detail="This list has no warranty")
        try:
            update["warranty"] = normalize_warranty(body.warranty)
        except ValueError as e:
            raise _bad(e)
    if body.active is not None:
        update["active"] = body.active

    if update:
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.catalog_items.update_one({"_id": oid}, {"$set": update})
        doc.update(update)
    return {"success": True, "data": item_to_out(doc)}
