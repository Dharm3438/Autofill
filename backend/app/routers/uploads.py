"""
Admin document uploads.

Three per-customer documents the admin supplies manually:
  • installation  — a single installation photo, converted to a one-page PDF
  • np_stamp      — the NP-Agreement first page printed on ₹100 stamp paper,
                    signed/stamped and scanned back as a PDF (merged in front
                    of the generated NP agreement at delivery time)
  • dcr           — the official DCR PDF downloaded from the government portal

Stored under the protected sub-prefix customers/{id}/uploads/ so document
regeneration (which wipes generated PDFs) never deletes them.
"""
import io
import asyncio
from PIL import Image, ImageOps
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from bson import ObjectId

from ..core.database import get_db
from ..core.permissions import P, require, parse_object_id
from ..services import storage
from ..services.doc_generation import (
    DOWNLOAD_LINK_SECONDS,
    INSTALLATION_UPLOAD_KEY,
    DCR_UPLOAD_KEY,
    NP_STAMP_UPLOAD_KEY,
    uploaded_docs_present,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

# kind -> (storage key suffix, customer.uploads flag)
UPLOAD_KINDS = {
    "installation": (INSTALLATION_UPLOAD_KEY, "installation"),
    "np_stamp":     (NP_STAMP_UPLOAD_KEY,     "np_stamp"),
    "dcr":          (DCR_UPLOAD_KEY,          "dcr"),
}

MAX_BYTES = 15 * 1024 * 1024  # 15 MB per upload


async def _get_customer(db, customer_id: str) -> dict:
    customer = await db.customers.find_one({"_id": parse_object_id(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


async def _read_limited(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 15 MB limit")
    return data


# The installation photo is shown on screen and printed at most page-size, so a
# full phone photo (4000 px, ~1.2 MB as a PDF) only costs bandwidth and storage
# every time it is saved, previewed or zipped. 1600 px is plenty for A4.
INSTALLATION_PHOTO_MAX_PX = 1600
INSTALLATION_PHOTO_QUALITY = 80


def _image_to_pdf(raw: bytes) -> bytes:
    """Convert a single image to a one-page PDF, shrunk to at most
    INSTALLATION_PHOTO_MAX_PX on its long side."""
    try:
        img = Image.open(io.BytesIO(raw))
        # Phones store the camera's rotation as an EXIF tag; apply it so the
        # photo isn't sideways once the tag is dropped by re-encoding.
        img = ImageOps.exif_transpose(img)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image. Upload a valid JPG/PNG.")
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((INSTALLATION_PHOTO_MAX_PX, INSTALLATION_PHOTO_MAX_PX), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PDF", quality=INSTALLATION_PHOTO_QUALITY)
    return out.getvalue()


def _ensure_pdf(raw: bytes):
    if not raw.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="File must be a PDF")


async def _set_upload_flag(db, customer_id: str, flag: str, value: bool):
    await db.customers.update_one(
        {"_id": parse_object_id(customer_id)},
        {"$set": {f"uploads.{flag}": value}},
    )


@router.get("/{customer_id}")
async def get_upload_status(customer_id: str, _=Depends(require(P.UPLOADS_MANAGE))):
    """Report which uploads actually exist in R2, and re-sync the Mongo flags
    so the customer list / Send-link gating can never drift from reality."""
    db = get_db()
    await _get_customer(db, customer_id)
    prefix = storage.customer_prefix(customer_id)
    status = await asyncio.to_thread(uploaded_docs_present, prefix)
    await db.customers.update_one({"_id": parse_object_id(customer_id)}, {"$set": {"uploads": status}})
    return {"success": True, "data": status}


@router.post("/{customer_id}/installation")
async def upload_installation(customer_id: str, file: UploadFile = File(...), _=Depends(require(P.UPLOADS_MANAGE))):
    db = get_db()
    await _get_customer(db, customer_id)
    raw = await _read_limited(file)
    pdf = await asyncio.to_thread(_image_to_pdf, raw)

    key = storage.customer_prefix(customer_id) + INSTALLATION_UPLOAD_KEY
    await asyncio.to_thread(storage.upload_bytes, pdf, key, "application/pdf")
    await _set_upload_flag(db, customer_id, "installation", True)
    return {"success": True, "message": "Installation photo uploaded"}


@router.post("/{customer_id}/np-stamp")
async def upload_np_stamp(customer_id: str, file: UploadFile = File(...), _=Depends(require(P.UPLOADS_MANAGE))):
    db = get_db()
    await _get_customer(db, customer_id)
    raw = await _read_limited(file)
    _ensure_pdf(raw)

    key = storage.customer_prefix(customer_id) + NP_STAMP_UPLOAD_KEY
    await asyncio.to_thread(storage.upload_bytes, raw, key, "application/pdf")
    await _set_upload_flag(db, customer_id, "np_stamp", True)
    return {"success": True, "message": "Stamped NP first page uploaded"}


@router.post("/{customer_id}/dcr")
async def upload_dcr(customer_id: str, file: UploadFile = File(...), _=Depends(require(P.UPLOADS_MANAGE))):
    db = get_db()
    await _get_customer(db, customer_id)
    raw = await _read_limited(file)
    _ensure_pdf(raw)

    key = storage.customer_prefix(customer_id) + DCR_UPLOAD_KEY
    await asyncio.to_thread(storage.upload_bytes, raw, key, "application/pdf")
    await _set_upload_flag(db, customer_id, "dcr", True)
    return {"success": True, "message": "DCR document uploaded"}


@router.get("/{customer_id}/{kind}")
async def preview_upload(customer_id: str, kind: str, _=Depends(require(P.UPLOADS_MANAGE))):
    if kind not in UPLOAD_KINDS:
        raise HTTPException(status_code=404, detail="Unknown upload type")
    key_suffix, _flag = UPLOAD_KINDS[kind]
    key = storage.customer_prefix(customer_id) + key_suffix
    if not await asyncio.to_thread(storage.object_exists, key):
        raise HTTPException(status_code=404, detail="Not uploaded yet")
    data = await asyncio.to_thread(storage.download_bytes, key)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{kind}.pdf"'},
    )


@router.get("/{customer_id}/{kind}/link")
async def preview_upload_link(customer_id: str, kind: str, _=Depends(require(P.UPLOADS_MANAGE))):
    """A short-lived direct R2 link to an uploaded document, opened in a new
    tab, so the file doesn't pass through this server (R2 downloads are free)."""
    if kind not in UPLOAD_KINDS:
        raise HTTPException(status_code=404, detail="Unknown upload type")
    key_suffix, _flag = UPLOAD_KINDS[kind]
    key = storage.customer_prefix(customer_id) + key_suffix
    if not await asyncio.to_thread(storage.object_exists, key):
        raise HTTPException(status_code=404, detail="Not uploaded yet")
    url = storage.presigned_url(key, DOWNLOAD_LINK_SECONDS, filename=f"{kind}.pdf", content_type="application/pdf")
    return {"success": True, "data": {"url": url}}


@router.delete("/{customer_id}/{kind}")
async def delete_upload(customer_id: str, kind: str, _=Depends(require(P.UPLOADS_MANAGE))):
    if kind not in UPLOAD_KINDS:
        raise HTTPException(status_code=404, detail="Unknown upload type")
    db = get_db()
    await _get_customer(db, customer_id)
    key_suffix, flag = UPLOAD_KINDS[kind]
    key = storage.customer_prefix(customer_id) + key_suffix
    await asyncio.to_thread(storage.delete_prefix, key)
    await _set_upload_flag(db, customer_id, flag, False)
    return {"success": True, "message": "Upload removed"}
