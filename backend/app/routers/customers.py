import asyncio
import re

from fastapi import APIRouter, HTTPException, Depends, Query, Response, status
from ..core.database import get_db
from ..core.permissions import P, require, customer_scope, user_permissions, parse_object_id
from ..models.customer import CustomerCreate, CustomerUpdate, missing_required_fields
from ..services.customer_sheet import build_customer_details_pdf, details_sheet_filename
from ..models.installation import default_installation_steps
from datetime import datetime, timezone

router = APIRouter(prefix="/customers", tags=["customers"])

# Never sent to the browser — the UI doesn't use them and they're sensitive
# (signing_token is a bearer credential for the customer's signing page).
_INTERNAL_FIELDS = ("signing_token", "signing_token_expiry", "signing_manifest", "r2_prefix")
# Only for users who work on installations / payments.
_INSTALLATION_FIELDS = ("installation_steps", "received_payments", "received_payment", "total_payment")
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
    user=Depends(require(P.CUSTOMERS_READ_ALL, P.CUSTOMERS_READ_OWN, any_of=True)),
):
    db = get_db()
    query = {}
    if search:
        query["$or"] = [
            {"CONSUMER_NAME": {"$regex": re.escape(search), "$options": "i"}},
            {"CONSUMER_APP_NO": {"$regex": re.escape(search), "$options": "i"}},
            {"CONSUMER_PHONE": {"$regex": re.escape(search), "$options": "i"}},
        ]
    query = scoped(user, query)

    total = await db.customers.count_documents(query)
    cursor = db.customers.find(query).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
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
    query = {"CONSUMER_NO": consumer_no}
    if exclude_id:
        query["_id"] = {"$ne": parse_object_id(exclude_id)}
    existing = await db.customers.find_one(query, {"_id": 1})
    return {"success": True, "exists": existing is not None}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_customer(body: CustomerCreate, user=Depends(require(P.CUSTOMERS_CREATE))):
    _require_fields(body.model_dump())
    db = get_db()
    if body.CONSUMER_NO:
        existing = await db.customers.find_one({"CONSUMER_NO": body.CONSUMER_NO}, {"_id": 1})
        if existing:
            raise HTTPException(status_code=409, detail="Consumer number already exists")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        **_strip_document_fields(body.model_dump(), user),
        "doc_status": "none",
        "signing_status": "none",
        "uploads": {"installation": False, "np_stamp": False, "dcr": False},
        "installation_steps": default_installation_steps(),
        "signing_token": None,
        "r2_prefix": None,
        "created_by": str(user["_id"]),
        "created_by_name": user.get("name"),
        "updated_by": str(user["_id"]),
        "created_at": now,
        "updated_at": now,
    }
    result = await db.customers.insert_one(doc)
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
    _require_fields(body.model_dump(), partial=True)
    db = get_db()
    oid = parse_object_id(customer_id)
    # Scope check first: a customer outside this user's scope is a 404, and the
    # duplicate check below must not run (or leak) for records they can't see.
    if not await db.customers.find_one(scoped(user, {"_id": oid}), {"_id": 1}):
        raise HTTPException(status_code=404, detail="Customer not found")

    if body.CONSUMER_NO:
        existing = await db.customers.find_one(
            {"CONSUMER_NO": body.CONSUMER_NO, "_id": {"$ne": oid}},
            {"_id": 1},
        )
        if existing:
            raise HTTPException(status_code=409, detail="Consumer number already exists")
    # CustomerUpdate only contains the customer data fields, so status/ownership
    # fields (doc_status, created_by, payments, …) can't be written through here.
    update_data = {k: v for k, v in _strip_document_fields(body.model_dump(), user).items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = str(user["_id"])

    result = await db.customers.update_one(scoped(user, {"_id": oid}), {"$set": update_data})
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
