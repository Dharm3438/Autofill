import base64
import io
import asyncio
from PIL import Image
import random
import string
import zipfile
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ..core.config import settings
from ..core.database import get_db
from ..core.deps import get_current_user
from ..services import storage
from ..services.doc_generation import (
    SIGNATURE_KEY,
    AADHAR_FRONT_KEY,
    AADHAR_BACK_KEY,
)
from bson import ObjectId

router = APIRouter(prefix="/signing", tags=["signing"])


# ── Admin: send signing link ──────────────────────────────────────────────────

@router.post("/send-link/{customer_id}")
async def send_signing_link(customer_id: str, _=Depends(get_current_user)):
    db = get_db()
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not customer.get("CONSUMER_EMAIL"):
        raise HTTPException(status_code=400, detail="Customer has no email address")

    # All three admin documents must be uploaded before the customer is sent the
    # signing link, so they never receive an incomplete bundle. Check R2 directly
    # (authoritative) rather than trusting the cached Mongo flags.
    from ..services.doc_generation import uploaded_docs_present
    prefix = storage.customer_prefix(customer_id)
    present = await asyncio.to_thread(uploaded_docs_present, prefix)
    await db.customers.update_one({"_id": ObjectId(customer_id)}, {"$set": {"uploads": present}})
    missing = [label for flag, label in (
        ("installation", "Installation Photo"),
        ("np_stamp", "Stamped NP First Page"),
        ("dcr", "DCR Document"),
    ) if not present.get(flag)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Upload required document(s) before sending the link: {', '.join(missing)}",
        )

    from ..services.signing import create_signing_token, send_signing_email
    from ..services.doc_generation import build_signing_manifest
    token = await create_signing_token(db, customer_id)
    send_signing_email(customer, token)

    # Persist the document manifest now (one R2 LIST) so each review-page
    # document view resolves from this list instead of re-LISTing R2 every time.
    review_prefix = customer.get("r2_prefix") or prefix
    manifest = await build_signing_manifest(review_prefix, customer)

    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": {"signing_status": "sent", "signing_token": token,
                  "signing_manifest": manifest}}
    )
    return {"success": True, "message": "Signing link sent to customer"}


# ── Public: token verification (page load) ────────────────────────────────────

@router.get("/verify/{token}")
async def verify_token(token: str):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    if submission.get("expires_at") and submission["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=410, detail="This link has expired")
    if submission.get("submitted"):
        raise HTTPException(status_code=409, detail="Documents have already been signed")

    customer = await db.customers.find_one({"_id": ObjectId(submission["customer_id"])})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Documents the signing page shows for review (filled with the customer's
    # details). Prefer the manifest persisted at send-link time; fall back to a
    # live R2 listing for links sent before the manifest existed.
    manifest = customer.get("signing_manifest")
    if manifest is None:
        from ..services.doc_generation import signing_document_list
        prefix = customer.get("r2_prefix") or storage.customer_prefix(submission["customer_id"])
        objects = await asyncio.to_thread(storage.list_objects, prefix)
        manifest = signing_document_list(prefix, objects, customer)
    documents = [{"key": d["key"], "name": d["label"]} for d in manifest]

    return {"success": True, "data": {
        "customer_name": customer.get("CONSUMER_NAME"),
        "customer_email": customer.get("CONSUMER_EMAIL"),
        "app_no": customer.get("CONSUMER_APP_NO"),
        "documents": documents,
    }}


# ── Public: stream a single document inline (PDF.js review viewer) ────────────

@router.get("/document/{token}/{key}")
async def get_signing_document(token: str, key: str):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid link")
    if submission.get("expires_at") and submission["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=410, detail="This link has expired")

    customer = await db.customers.find_one({"_id": ObjectId(submission["customer_id"])})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    from ..services.doc_generation import fetch_signing_document
    prefix = customer.get("r2_prefix") or storage.customer_prefix(submission["customer_id"])
    result = await fetch_signing_document(prefix, customer, key, customer.get("signing_manifest"))
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")

    name, data = result
    # Content-Disposition is encoded as latin-1, so the filename must be ASCII —
    # labels like "Annexure-1 — …" contain an em dash that would 500 the request.
    import unicodedata
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    ascii_name = " ".join(ascii_name.replace('"', "").split()) or "document"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{ascii_name}.pdf"',
            "Cache-Control": "private, max-age=600",
        },
    )


# ── Public: send OTP to customer email ───────────────────────────────────────

@router.post("/send-otp/{token}")
async def send_otp(token: str, force: bool = False):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid link")

    customer = await db.customers.find_one({"_id": ObjectId(submission["customer_id"])})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now(timezone.utc).isoformat()
    existing_otp = submission.get("otp")
    existing_expiry = submission.get("otp_expiry")
    has_valid_otp = (
        existing_otp
        and not submission.get("otp_verified")
        and existing_expiry
        and existing_expiry > now
    )

    if has_valid_otp:
        # A live code already exists. Don't email again on auto-sends (page
        # reloads / re-clicking the email link) — only when the user explicitly
        # asks to resend. Either way we keep the same code so the OTP already in
        # their inbox stays valid.
        otp = existing_otp
        if not force:
            return {"success": True, "message": "OTP already sent"}
    else:
        otp = "".join(random.choices(string.digits, k=6))
        otp_expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        await db.signing_submissions.update_one(
            {"token": token},
            {"$set": {"otp": otp, "otp_expiry": otp_expiry, "otp_verified": False}}
        )

    from ..services.signing import send_otp_email
    send_otp_email(customer, otp)

    return {"success": True, "message": "OTP sent to customer email"}


# ── Public: verify OTP ────────────────────────────────────────────────────────

class OTPBody(BaseModel):
    otp: str

@router.post("/verify-otp/{token}")
async def verify_otp(token: str, body: OTPBody):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid link")
    if submission.get("otp_verified"):
        return {"success": True, "message": "Already verified"}
    if submission.get("otp") != body.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if submission.get("otp_expiry") and submission["otp_expiry"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

    await db.signing_submissions.update_one(
        {"token": token},
        {"$set": {"otp_verified": True}}
    )
    return {"success": True, "message": "OTP verified"}


# ── Public: submit signature + Aadhaar card (front + back) ───────────────────

class SubmitBody(BaseModel):
    signature: str | None = None       # base64 data URL
    aadhar_front: str | None = None    # base64 data URL
    aadhar_back: str | None = None     # base64 data URL

@router.post("/submit/{token}")
async def submit_signing(token: str, body: SubmitBody, background_tasks: BackgroundTasks):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid link")
    if not submission.get("otp_verified"):
        raise HTTPException(status_code=403, detail="OTP not verified")
    if submission.get("submitted"):
        raise HTTPException(status_code=409, detail="Already submitted")

    customer_id = submission["customer_id"]
    customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Save signature + Aadhaar card (front & back) to R2 under the customer's
    # prefix. Aadhaar images stay full-colour JPEGs (no black/white filter).
    prefix = storage.customer_prefix(customer_id)
    sig_bytes = _decode_base64_image(body.signature)
    front_bytes = _decode_base64_image(body.aadhar_front)
    back_bytes = _decode_base64_image(body.aadhar_back)
    if sig_bytes:
        sig_bytes = _compress_signature(sig_bytes)
        await asyncio.to_thread(storage.upload_bytes, sig_bytes, prefix + SIGNATURE_KEY, "image/png")
    if front_bytes:
        front_bytes = _compress_photo(front_bytes)
        await asyncio.to_thread(storage.upload_bytes, front_bytes, prefix + AADHAR_FRONT_KEY, "image/jpeg")
    if back_bytes:
        back_bytes = _compress_photo(back_bytes)
        await asyncio.to_thread(storage.upload_bytes, back_bytes, prefix + AADHAR_BACK_KEY, "image/jpeg")

    now = datetime.now(timezone.utc)
    download_expires_at = (now + timedelta(days=settings.DOWNLOAD_WINDOW_DAYS)).isoformat()
    await db.signing_submissions.update_one(
        {"token": token},
        {"$set": {
            "submitted": True,
            "submitted_at": now.isoformat(),
            "download_expires_at": download_expires_at,
        }}
    )
    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": {"signing_status": "signed", "doc_status": "generating"}}
    )

    # Regenerate docs so they embed the freshly-saved signature & photo
    background_tasks.add_task(_regen_after_signing, customer_id)

    return {"success": True, "message": "Documents signed successfully"}


# ── Public: download finalized documents (after signing) ─────────────────────

@router.get("/download/{token}")
async def download_signed_docs(token: str):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid link")
    if not submission.get("submitted"):
        raise HTTPException(status_code=403, detail="Documents have not been signed yet")

    expires_at = submission.get("download_expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=410, detail="The download window for these documents has expired.")

    customer = await db.customers.find_one({"_id": ObjectId(submission["customer_id"])})
    if not customer or not customer.get("r2_prefix"):
        raise HTTPException(status_code=404, detail="No documents found")

    if customer.get("doc_status") == "generating":
        raise HTTPException(status_code=425, detail="Your documents are still being finalized. Please try again in a few seconds.")

    from ..services.doc_generation import build_customer_bundle
    bundle = await build_customer_bundle(customer["r2_prefix"])
    if not bundle:
        raise HTTPException(status_code=404, detail="No finalized documents available")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in bundle:
            zf.writestr(name, data)
    buf.seek(0)

    safe_name = customer.get("CONSUMER_NAME", "documents").replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_signed_docs.zip"},
    )


async def _regen_after_signing(customer_id: str):
    from ..services.doc_generation import generate_for_customer
    db = get_db()
    try:
        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            return
        prefix = await generate_for_customer(customer)
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "complete", "r2_prefix": prefix}}
        )
        print(f"Re-generated signed docs for {customer_id}")
    except Exception as e:
        print(f"Regen after signing failed for {customer_id}: {e}")
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "failed"}}
        )


def _decode_base64_image(data_url: str) -> bytes | None:
    if not data_url:
        return None
    try:
        encoded = data_url.split(",", 1)[1] if "," in data_url else data_url
        return base64.b64decode(encoded)
    except Exception as e:
        print(f"Failed to decode image: {e}")
        return None


def _compress_signature(raw: bytes, max_bytes: int = 5 * 1024 * 1024) -> bytes:
    """Resize signature to max 800×400 px and re-encode as PNG."""
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img.thumbnail((800, 400), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _compress_photo(raw: bytes, max_bytes: int = 5 * 1024 * 1024) -> bytes:
    """Resize photo to max 1200×1600 px and re-encode as JPEG, reducing quality until under max_bytes."""
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.thumbnail((1200, 1600), Image.LANCZOS)
    quality = 85
    while quality >= 50:
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        if out.tell() <= max_bytes:
            return out.getvalue()
        quality -= 10
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=50, optimize=True)
    return out.getvalue()
