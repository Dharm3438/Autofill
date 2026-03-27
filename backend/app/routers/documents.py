import io
import zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from ..core.database import get_db
from ..core.deps import get_current_user
from ..services.doc_generation import OUTPUT_DIR
from bson import ObjectId

router = APIRouter(prefix="/documents", tags=["documents"])


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
        folder = await generate_for_customer(customer)
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "complete", "docs_folder": folder}}
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
        {"doc_status": 1, "docs_folder": 1}
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"success": True, "data": {
        "doc_status": customer.get("doc_status", "none"),
        "docs_folder": customer.get("docs_folder"),
    }}


@router.get("/list/{customer_id}")
async def list_documents(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)}, {"docs_folder": 1})
    if not customer or not customer.get("docs_folder"):
        raise HTTPException(status_code=404, detail="No documents found")

    folder = OUTPUT_DIR / customer["docs_folder"]
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Documents folder not found on server")

    files = [
        {"name": f.name, "size": f.stat().st_size, "type": f.suffix.lstrip(".")}
        for f in sorted(folder.iterdir())
        if f.is_file()
    ]
    return {"success": True, "data": files}


@router.get("/download/{customer_id}/zip")
async def download_zip(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not customer or not customer.get("docs_folder"):
        raise HTTPException(status_code=404, detail="No documents found")

    folder = OUTPUT_DIR / customer["docs_folder"]
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Documents folder not found on server")

    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder.iterdir():
            if f.is_file():
                zf.write(f, f.name)
    buf.seek(0)

    safe_name = customer.get("CONSUMER_NAME", "documents").replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_docs.zip"}
    )
