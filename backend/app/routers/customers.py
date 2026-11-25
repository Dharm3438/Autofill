import asyncio
import re

from fastapi import APIRouter, HTTPException, Depends, Query, Response, status
from pymongo.errors import DuplicateKeyError
from ..core.database import get_db
from ..core.permissions import P, require, customer_scope, user_permissions, parse_object_id
from ..models.customer import CustomerCreate, CustomerUpdate, missing_required_fields, derived_fields
from ..services.customer_sheet import build_customer_details_pdf, details_sheet_filename
from ..models.installation import default_installation_steps
from datetime import datetime, timezone

router = APIRouter(prefix="/customers", tags=["customers"])

# Never sent to the browser — the UI doesn't use them and they're sensitive
# (signing_token is a bearer credential for the customer's signing page).
_INTERNAL_FIELDS = ("signing_token", "signing_token_expiry", "signing_manifest", "r2_prefix")
# Only for users who work on installations / payments.
_INSTALLATION_FIELDS = ("installation_steps", "received_payments")
# Only for users who work on documents.
_DOCUMENT_FIELDS = ("doc_status", "signing_status", "uploads", "AGREEMENT_SYSTEM_COST")
# Customer data fields that only document users may write. Silently dropped for
# everyone else so a form sending "" for them can't blank or set the value.
_DOCUMENT_WRITE_FIELDS = ("AGREEMENT_SYSTEM_COST",)


def _strip_document_fields(data: dict, user: dict) -> dict:
    if P.DOCUMENTS_MANAGE not in user_permissions(user):
        for f in _DOCUMENT_WRITE_FIELDS:
            data.pop(f, None)
    return data


def customer_to_out(c: dict, user: dict) -> dict:
    """Shape a customer document for this user: drop whatever their role doesn't need."""
    perms = user_permissions(user)
    out = dict(c)
    out["id"] = str(out.pop("_id"))
    for f in _INTERNAL_FIELDS:
        out.pop(f, None)
    if P.INSTALLATIONS_READ not in perms:
        for f in _INSTALLATION_FIELDS:
            out.pop(f, None)
    if P.DOCUMENTS_MANAGE not in perms:
        for f in _DOCUMENT_FIELDS:
            out.pop(f, None)
    return out


def scoped(user: dict, query: dict) -> dict:
    """AND the caller's query with the user's visibility scope."""
    scope = customer_scope(user)
    if not scope:
        return query
    if not query:
        return scope
    return {"$and": [query, scope]}


# Customer list sort orders. Each ends in _id so paging is stable. Missing
# values (null) sort last when descending and first when ascending.
LIST_SORTS = {
    "newest":        [("created_at", -1), ("_id", -1)],
    "oldest":        [("created_at", 1), ("_id", 1)],
    "name":          [("CONSUMER_NAME", 1), ("_id", 1)],
    "app_date_desc": [("CONSUMER_APP_DATE", -1), ("_id", -1)],
    "app_date_asc":  [("CONSUMER_APP_DATE", 1), ("_id", 1)],
    "cost_desc":     [("SYSTEM_COST", -1), ("_id", -1)],
    "cost_asc":      [("SYSTEM_COST", 1), ("_id", 1)],
    "capacity_desc": [("SOLAR_CAPACITY", -1), ("_id", -1)],
}

# Names sort case-insensitively (English, case-insensitive collation).
_NAME_COLLATION = {"locale": "en", "strength": 2}


def _require_fields(data: dict, partial: bool = False) -> None:
    missing = missing_required_fields(data, partial=partial)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Please fill the required fields: {', '.join(missing)}",
        )


@router.get("")
async def list_customers(
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="newest"),
    user=Depends(require(P.CUSTOMERS_READ_ALL, P.CUSTOMERS_READ_OWN, any_of=True)),
):
    sort_spec = LIST_SORTS.get(sort)
    if sort_spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown sort: {sort}")
    db = get_db()
    query = {}
    if search:
        query["$or"] = [
            {"CONSUMER_NAME": {"$regex": re.escape(search), "$options": "i"}},
            {"CONSUMER_APP_NO": {"$regex": re.escape(search), "$options": "i"}},
            {"SUBSIDY_APP_NO": {"$regex": re.escape(search), "$options": "i"}},
            {"CONSUMER_PHONE": {"$regex": re.escape(search), "$options": "i"}},
        ]
    query = scoped(user, query)

    total = await db.customers.count_documents(query)
    cursor = db.customers.find(query).sort(sort_spec).skip((page - 1) * limit).limit(limit)
    if sort == "name":
        cursor = cursor.collation(_NAME_COLLATION)
    customers = [customer_to_out(c, user) async for c in cursor]

    return {"success": True, "data": customers, "total": total, "page": page, "limit": limit}


@router.get("/check-consumer-no")
async def check_consumer_no(
    consumer_no: str = Query(...),
    exclude_id: str = Query(default=None),
    _=Depends(require(P.CUSTOMERS_CREATE, P.CUSTOMERS_UPDATE, any_of=True)),
):
    # Deliberately global (not scoped): duplicates must be caught across all
    # customers. Only a yes/no is returned, never whose record it is.
    db = get_db()
    query = {"CONSUMER_NO": re.sub(r"\s+", "", consumer_no)}
    if exclude_id:
        query["_id"] = {"$ne": parse_object_id(exclude_id)}
    existing = await db.customers.find_one(query, {"_id": 1})
    return {"success": True, "exists": existing is not None}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_customer(body: CustomerCreate, user=Depends(require(P.CUSTOMERS_CREATE))):
    data = _strip_document_fields(body.to_store(), user)
    _require_fields(data)
    db = get_db()
    if await db.customers.find_one({"CONSUMER_NO": data["CONSUMER_NO"]}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Consumer number already exists")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        **data,
        **derived_fields(data),
        "doc_status": "none",
        "signing_status": "none",
        "uploads": {"installation": False, "np_stamp": False, "dcr": False},
        "installation_steps": default_installation_steps(),
        "received_payments": [],
        "INSTALLATION_DATE": None,
        "signing_token": None,
        "r2_prefix": None,
        "created_by": str(user["_id"]),
        "created_by_name": user.get("name"),
        "updated_by": str(user["_id"]),
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db.customers.insert_one(doc)
    except DuplicateKeyError:
        # Two saves of the same consumer no at once: the unique index wins.
        raise HTTPException(status_code=409, detail="Consumer number already exists")
    doc["_id"] = result.inserted_id
    return {"success": True, "data": customer_to_out(doc, user)}


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    user=Depends(require(P.CUSTOMERS_READ_ALL, P.CUSTOMERS_READ_OWN, any_of=True)),
):
    db = get_db()
    c = await db.customers.find_one(scoped(user, {"_id": parse_object_id(customer_id)}))
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"success": True, "data": customer_to_out(c, user)}


@router.get("/{customer_id}/details-sheet")
async def customer_details_sheet(customer_id: str, _=Depends(require(P.DOCUMENTS_MANAGE))):
    """The filled one-page Customer Details PDF, opened inline for printing."""
    db = get_db()
    c = await db.customers.find_one({"_id": parse_object_id(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    pdf = await asyncio.to_thread(build_customer_details_pdf, c)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{details_sheet_filename(c)}"'},
    )


@router.put("/{customer_id}")
async def update_customer(customer_id: str, body: CustomerUpdate, user=Depends(require(P.CUSTOMERS_UPDATE))):
    # Only the fields the request sent; one sent blank (null) clears it.
    update_data = _strip_document_fields(body.to_store(only_sent=True), user)
    _require_fields(update_data, partial=True)
    db = get_db()
    oid = parse_object_id(customer_id)
    # Scope check first: a customer outside this user's scope is a 404, and the
    # duplicate check below must not run (or leak) for records they can't see.
    current = await db.customers.find_one(scoped(user, {"_id": oid}))
    if not current:
        raise HTTPException(status_code=404, detail="Customer not found")

    if update_data.get("CONSUMER_NO"):
        existing = await db.customers.find_one(
            {"CONSUMER_NO": update_data["CONSUMER_NO"], "_id": {"$ne": oid}},
            {"_id": 1},
        )
        if existing:
            raise HTTPException(status_code=409, detail="Consumer number already exists")
    # CustomerUpdate only contains the customer data fields, so status/ownership
    # fields (doc_status, created_by, payments, …) can't be written through here.
    # Derived fields are recomputed from the merged record.
    update_data.update(derived_fields({**current, **update_data}))
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = str(user["_id"])

    try:
        result = await db.customers.update_one(scoped(user, {"_id": oid}), {"$set": update_data})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Consumer number already exists")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")

    c = await db.customers.find_one({"_id": oid})
    return {"success": True, "data": customer_to_out(c, user)}


@router.delete("/{customer_id}", status_code=status.HTTP_200_OK)
async def delete_customer(customer_id: str, _=Depends(require(P.CUSTOMERS_DELETE))):
    db = get_db()
    result = await db.customers.delete_one({"_id": parse_object_id(customer_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"success": True, "message": "Customer deleted"}
