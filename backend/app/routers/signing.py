import base64
import io
import asyncio
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
from ..services.doc_generation import SIGNATURE_KEY, PHOTO_KEY
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

    from ..services.signing import create_signing_token, send_signing_email
    token = await create_signing_token(db, customer_id)
    send_signing_email(customer, token)

    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": {"signing_status": "sent", "signing_token": token}}
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

    return {"success": True, "data": {
        "customer_name": customer.get("CONSUMER_NAME"),
        "customer_email": customer.get("CONSUMER_EMAIL"),
        "app_no": customer.get("CONSUMER_APP_NO"),
    }}


# ── Public: send OTP to customer email ───────────────────────────────────────

@router.post("/send-otp/{token}")
async def send_otp(token: str):
    db = get_db()
    submission = await db.signing_submissions.find_one({"token": token})
    if not submission:
        raise HTTPException(status_code=404, detail="Invalid link")

    customer = await db.customers.find_one({"_id": ObjectId(submission["customer_id"])})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

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


# ── Public: submit signature + photo ─────────────────────────────────────────

class SubmitBody(BaseModel):
    signature: str   # base64 data URL
    photo: str       # base64 data URL

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

    # Save signature and photo to R2 under the customer's prefix
    prefix = storage.customer_prefix(customer_id)
    sig_bytes = _decode_base64_image(body.signature)
    photo_bytes = _decode_base64_image(body.photo)
    if sig_bytes:
        await asyncio.to_thread(storage.upload_bytes, sig_bytes, prefix + SIGNATURE_KEY, "image/png")
    if photo_bytes:
        await asyncio.to_thread(storage.upload_bytes, photo_bytes, prefix + PHOTO_KEY, "image/jpeg")

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

    objects = [o for o in await asyncio.to_thread(storage.list_objects, customer["r2_prefix"])
               if o["name"].lower().endswith(".pdf")]
    if not objects:
        raise HTTPException(status_code=404, detail="No finalized documents available")

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
    # data_url: "data:image/png;base64,xxxxxx"
    if not data_url:
        return None
    try:
        encoded = data_url.split(",", 1)[1] if "," in data_url else data_url
        return base64.b64decode(encoded)
    except Exception as e:
        print(f"Failed to decode image: {e}")
        return None
