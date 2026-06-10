import io
import asyncio
import zipfile
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from ..core.database import get_db
from ..core.deps import get_current_user
from ..services import storage
from bson import ObjectId

router = APIRouter(prefix="/documents", tags=["documents"])

_PRIVATE_NAMES = {"signature.png", "photo.jpg"}

# Suffix of the generated PDF for the NP Agreement first page (see doc_generation.TEMPLATES)
_NP_FIRST_PAGE_SUFFIX = "_NP_Agreement_First_Page.pdf"


@router.post("/generate/{customer_id}")
async def generate_documents(
    customer_id: str,
    background_tasks: BackgroundTasks,
    _=Depends(get_current_user),
):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if customer.get("doc_status") == "generating":
        raise HTTPException(status_code=400, detail="Document generation already in progress")

    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": {"doc_status": "generating"}}
    )

    background_tasks.add_task(_generate_task, customer_id, customer)
    return {"success": True, "message": "Document generation started"}


async def _generate_task(customer_id: str, customer: dict):
    from ..services.doc_generation import generate_for_customer
    from ..core.database import get_db
    db = get_db()
    try:
        prefix = await generate_for_customer(customer)
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "complete", "r2_prefix": prefix}}
        )
        print(f"Docs complete for {customer_id}")
    except Exception as e:
        print(f"Doc generation failed for {customer_id}: {e}")
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "failed"}}
        )


@router.get("/status/{customer_id}")
async def get_doc_status(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one(
        {"_id": ObjectId(customer_id)},
        {"doc_status": 1, "r2_prefix": 1}
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"success": True, "data": {
        "doc_status": customer.get("doc_status", "none"),
        "r2_prefix": customer.get("r2_prefix"),
    }}


@router.get("/list/{customer_id}")
async def list_documents(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)}, {"r2_prefix": 1})
    if not customer or not customer.get("r2_prefix"):
        raise HTTPException(status_code=404, detail="No documents found")

    objects = await asyncio.to_thread(storage.list_objects, customer["r2_prefix"])
    files = [
        {"name": o["name"], "size": o["size"], "type": o["name"].rsplit(".", 1)[-1] if "." in o["name"] else ""}
        for o in sorted(objects, key=lambda o: o["name"])
        if o["name"] not in _PRIVATE_NAMES and not o["name"].endswith(_NP_FIRST_PAGE_SUFFIX)
    ]
    return {"success": True, "data": files}


@router.get("/download/{customer_id}/np-first-page")
async def download_np_first_page(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not customer or not customer.get("r2_prefix"):
        raise HTTPException(status_code=404, detail="No documents found")

    objects = await asyncio.to_thread(storage.list_objects, customer["r2_prefix"])
    target = next((o for o in objects if o["name"].endswith(_NP_FIRST_PAGE_SUFFIX)), None)
    if not target:
        raise HTTPException(status_code=404, detail="NP Agreement first page not found")

    data = await asyncio.to_thread(storage.download_bytes, target["key"])
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{target["name"]}"'}
    )


@router.get("/download/{customer_id}/zip")
async def download_zip(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not customer or not customer.get("r2_prefix"):
        raise HTTPException(status_code=404, detail="No documents found")

    prefix = customer["r2_prefix"]
    objects = [o for o in await asyncio.to_thread(storage.list_objects, prefix)
               if o["name"] not in _PRIVATE_NAMES and not o["name"].endswith(_NP_FIRST_PAGE_SUFFIX)]
    if not objects:
        raise HTTPException(status_code=404, detail="No documents found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for o in objects:
            data = await asyncio.to_thread(storage.download_bytes, o["key"])
            zf.writestr(o["name"], data)
    buf.seek(0)

    safe_name = customer.get("CONSUMER_NAME", "documents").replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_docs.zip"}
    )
