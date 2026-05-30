import base64
import io
import random
import string
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ..core.database import get_db
from ..core.deps import get_current_user
from ..services.doc_generation import OUTPUT_DIR
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

    # Save signature and photo files to customer's docs folder
    docs_folder = customer.get("docs_folder")
    if docs_folder:
        folder = OUTPUT_DIR / docs_folder
        folder.mkdir(parents=True, exist_ok=True)

        sig_path   = folder / "signature.png"
        photo_path = folder / "photo.jpg"

        _save_base64_image(body.signature, sig_path)
        _save_base64_image(body.photo, photo_path)

    now = datetime.now(timezone.utc).isoformat()
    await db.signing_submissions.update_one(
        {"token": token},
        {"$set": {"submitted": True, "submitted_at": now}}
    )
    await db.customers.update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": {"signing_status": "signed"}}
    )

    # Regenerate docs so they embed the freshly-saved signature & photo
    if docs_folder:
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "generating"}}
        )
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

    customer = await db.customers.find_one({"_id": ObjectId(submission["customer_id"])})
    if not customer or not customer.get("docs_folder"):
        raise HTTPException(status_code=404, detail="No documents found")

    if customer.get("doc_status") == "generating":
        raise HTTPException(status_code=425, detail="Your documents are still being finalized. Please try again in a few seconds.")

    folder = OUTPUT_DIR / customer["docs_folder"]
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Documents folder not found on server")

    pdfs = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
    files = pdfs if pdfs else [
        f for f in folder.iterdir()
        if f.is_file() and f.name not in ("signature.png", "photo.jpg")
    ]
    if not files:
        raise HTTPException(status_code=404, detail="No finalized documents available")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
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
        folder = await generate_for_customer(customer)
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "complete", "docs_folder": folder}}
        )
        print(f"Re-generated signed docs for {customer_id}")
    except Exception as e:
        print(f"Regen after signing failed for {customer_id}: {e}")
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"doc_status": "failed"}}
        )


def _save_base64_image(data_url: str, path: Path):
    # data_url: "data:image/png;base64,xxxxxx"
    try:
        header, encoded = data_url.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        path.write_bytes(img_bytes)
    except Exception as e:
        print(f"Failed to save image {path}: {e}")
