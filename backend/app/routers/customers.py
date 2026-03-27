from fastapi import APIRouter, HTTPException, Depends, Query, status
from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.customer import CustomerCreate, CustomerUpdate, CustomerOut
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/customers", tags=["customers"])


def customer_to_out(c: dict) -> dict:
    c["id"] = str(c.pop("_id"))
    return c


@router.get("")
async def list_customers(
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _=Depends(get_current_user),
):
    db = get_db()
    query = {}
    if search:
        query["$or"] = [
            {"CONSUMER_NAME": {"$regex": search, "$options": "i"}},
            {"CONSUMER_APP_NO": {"$regex": search, "$options": "i"}},
            {"CONSUMER_PHONE": {"$regex": search, "$options": "i"}},
        ]

    total = await db.customers.count_documents(query)
    cursor = db.customers.find(query).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
    customers = [customer_to_out(c) async for c in cursor]

    return {"success": True, "data": customers, "total": total, "page": page, "limit": limit}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_customer(body: CustomerCreate, _=Depends(get_current_user)):
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        **body.model_dump(),
        "doc_status": "none",
        "signing_status": "none",
        "signing_token": None,
        "docs_folder": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.customers.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return {"success": True, "data": doc}


@router.get("/{customer_id}")
async def get_customer(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    c = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"success": True, "data": customer_to_out(c)}


@router.put("/{customer_id}")
async def update_customer(customer_id: str, body: CustomerUpdate, _=Depends(get_current_user)):
    db = get_db()
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")

    c = await db.customers.find_one({"_id": ObjectId(customer_id)})
    return {"success": True, "data": customer_to_out(c)}


@router.delete("/{customer_id}", status_code=status.HTTP_200_OK)
async def delete_customer(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    result = await db.customers.delete_one({"_id": ObjectId(customer_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"success": True, "message": "Customer deleted"}
