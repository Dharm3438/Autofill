"""
Document generation service.
Fills DOCX templates with customer data and converts to PDF.
Windows: uses MS Word via docx2pdf. Linux: uses LibreOffice headless via subprocess.
"""
import re
import sys
import shutil
import asyncio
import tempfile
import subprocess
from pathlib import Path
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches

from . import storage

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "DOCS"

SIGNATURE_KEY = "signature.png"
PHOTO_KEY = "photo.jpg"
# Customer Aadhaar card images collected on the signing page.
AADHAR_FRONT_KEY = "aadhar_front.jpg"
AADHAR_BACK_KEY = "aadhar_back.jpg"

TEMPLATES = {
    "Annexure_1":           "TEMPELATE_Annexure.docx",
    "Aadhar":               "Aadhar.docx",
    "WCR":                  "WCR.docx",
    "Annexure_3":           "Annexure-3-Net-Metering.docx",
    "NP_Agreement":         "np_agreement.docx",
    "NP_Agreement_First_Page": "np_agreement_first_page.docx",
    "Meter_testing_letter": "Meter Testing Letter.docx",
    # DCR is no longer auto-generated — the admin uploads the official
    # government DCR PDF (see uploads router / DCR_UPLOAD_KEY below).
}

# ── Admin-uploaded documents (stored under a protected sub-prefix) ────────────
# These live under customers/{id}/uploads/ so the "delete all PDFs before
# regeneration" step never wipes them when the customer signs.
UPLOAD_PREFIX = "uploads/"
INSTALLATION_UPLOAD_KEY = UPLOAD_PREFIX + "installation.pdf"
DCR_UPLOAD_KEY          = UPLOAD_PREFIX + "dcr.pdf"
NP_STAMP_UPLOAD_KEY     = UPLOAD_PREFIX + "np_first_page_stamped.pdf"

# Friendly filenames for uploaded extras in the delivered bundle.
INSTALLATION_OUT_NAME = "Customer_Installation_Photo.pdf"
DCR_OUT_NAME          = "DCR.pdf"

# Internal artifacts that are never delivered to the customer.
HIDDEN_DOC_NAMES = {SIGNATURE_KEY, PHOTO_KEY, AADHAR_FRONT_KEY, AADHAR_BACK_KEY}
# Generated, unstamped NP first page — for the admin to print only.
NP_FIRST_PAGE_SUFFIX = "_NP_Agreement_First_Page.pdf"
# Base NP agreement (pages 2+). The stamped first page is merged in front of it.
NP_AGREEMENT_SUFFIX = "_NP_Agreement.pdf"

# placeholder -> (image-key, render width)
IMAGE_PLACEHOLDERS = {
    "${CUSTOMER_SIGN}$":   ("signature",    Inches(1.25)),
    "${CUSTOMER_PHOTO}$":  ("photo",        Inches(2.5)),
    # Aadhaar card images uploaded by the customer on the signing page.
    "${AADHAR_FRONT}$":    ("aadhar_front", Inches(3.0)),
    "${AADHAR_BACK}$":     ("aadhar_back",  Inches(3.0)),
}


def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", str(name)).strip()


def build_replacements(customer: dict) -> dict:
    replacements = {}
    for key, value in customer.items():
        if key.startswith("_") or value is None:
            continue
        replacements[f"${{{key}}}$"] = str(value) if value else ""
    return replacements


def process_paragraph(paragraph, replacements: dict, images: dict):
    all_keys = list(replacements.keys()) + list(IMAGE_PLACEHOLDERS.keys())
    original = "".join(r.text for r in paragraph.runs)
    if not any(k in original for k in all_keys):
        return
    for run in paragraph.runs:
        run.text = ""

    pattern = "|".join(re.escape(k) for k in all_keys)
    parts = re.split(f"({pattern})", original)
    for part in parts:
        if part in IMAGE_PLACEHOLDERS:
            img_key, width = IMAGE_PLACEHOLDERS[part]
            img_path = images.get(img_key)
            if img_path and img_path.exists():
                try:
                    new_run = paragraph.add_run()
                    new_run.add_picture(str(img_path), width=width)
                except Exception as e:
                    print(f"Failed to embed image {img_path}: {e}")
            # else: leave blank — image not available yet
        elif part in replacements:
            new_run = paragraph.add_run(replacements[part])
            new_run.bold = True
        else:
            paragraph.add_run(part)


def fill_template(template_path: Path, output_path: Path, replacements: dict, images: dict):
    doc = Document(template_path)
    for para in doc.paragraphs:
        process_paragraph(para, replacements, images)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    process_paragraph(para, replacements, images)
    doc.save(output_path)


def convert_docx_to_pdf(docx_path: Path) -> bool:
    try:
        pdf_path = docx_path.with_suffix(".pdf")
        if sys.platform == "win32":
            from docx2pdf import convert
            convert(str(docx_path), str(pdf_path))
        else:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf",
                 "--outdir", str(docx_path.parent), str(docx_path)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                print(f"LibreOffice error: {result.stderr}")
                return False
        return pdf_path.exists()
    except Exception as e:
        print(f"PDF conversion failed [{docx_path.name}]: {e}")
        return False


async def generate_for_customer(customer: dict) -> str:
    """
    Generate all documents for a customer in a temp dir, then upload the
    resulting PDFs to R2 under customers/{id}/. Returns the R2 prefix.
    """
    customer_id = str(customer.get("_id", "unknown"))
    safe_name = sanitize(customer.get("CONSUMER_NAME", "customer"))
    prefix = storage.customer_prefix(customer_id)

    replacements = build_replacements(customer)
    loop = asyncio.get_event_loop()

    work_dir = Path(tempfile.mkdtemp(prefix=f"docgen_{customer_id}_"))
    try:
        # Pull signature + Aadhaar images down from R2 (saved during signing) so they get embedded
        images = {}
        for img_key, fname in (("signature", SIGNATURE_KEY), ("photo", PHOTO_KEY),
                               ("aadhar_front", AADHAR_FRONT_KEY), ("aadhar_back", AADHAR_BACK_KEY)):
            r2_key = prefix + fname
            local = work_dir / fname
            if await loop.run_in_executor(None, storage.object_exists, r2_key):
                data = await loop.run_in_executor(None, storage.download_bytes, r2_key)
                local.write_bytes(data)
                images[img_key] = local
            else:
                images[img_key] = None

        # Remove any stale PDFs from a previous generation before uploading fresh
        # ones — but never touch admin uploads under the uploads/ sub-prefix.
        upload_prefix = prefix + UPLOAD_PREFIX
        stale = [o["key"] for o in await loop.run_in_executor(None, storage.list_objects, prefix)
                 if o["key"].lower().endswith(".pdf") and not o["key"].startswith(upload_prefix)]
        for key in stale:
            await loop.run_in_executor(None, storage.delete_prefix, key)

        for doc_type, template_file in TEMPLATES.items():
            template_path = TEMPLATE_DIR / template_file
            if not template_path.exists():
                print(f"Template not found: {template_path}")
                continue

            docx_path = work_dir / f"{safe_name}_{doc_type}.docx"
            await loop.run_in_executor(None, fill_template, template_path, docx_path, replacements, images)

            success = await loop.run_in_executor(None, convert_docx_to_pdf, docx_path)
            pdf_path = docx_path.with_suffix(".pdf")
            if success and pdf_path.exists():
                await loop.run_in_executor(
                    None, storage.upload_file, pdf_path, prefix + pdf_path.name, "application/pdf"
                )
                print(f"Uploaded to R2: {prefix + pdf_path.name}")
            else:
                print(f"PDF failed: {docx_path.stem}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return prefix


# ── Upload presence (authoritative — reads R2, not the Mongo flags) ──────────

def uploaded_docs_present(prefix: str) -> dict:
    """Return which admin uploads actually exist in R2 under `prefix`."""
    return {
        "installation": storage.object_exists(prefix + INSTALLATION_UPLOAD_KEY),
        "np_stamp":     storage.object_exists(prefix + NP_STAMP_UPLOAD_KEY),
        "dcr":          storage.object_exists(prefix + DCR_UPLOAD_KEY),
    }


# ── Final-bundle assembly (delivered to the customer / admin download) ────────

def merge_pdf_front(front: bytes, base: bytes) -> bytes:
    """Return a single PDF with `front` pages prepended to `base` pages."""
    out = fitz.open()
    front_doc = fitz.open(stream=front, filetype="pdf")
    base_doc = fitz.open(stream=base, filetype="pdf")
    try:
        out.insert_pdf(front_doc)
        out.insert_pdf(base_doc)
        return out.tobytes()
    finally:
        out.close()
        front_doc.close()
        base_doc.close()


def _is_deliverable(prefix: str, obj: dict) -> bool:
    """True for a generated PDF that should reach the customer."""
    key, name = obj["key"], obj["name"]
    if key.startswith(prefix + UPLOAD_PREFIX):      # admin uploads handled separately
        return False
    if name in HIDDEN_DOC_NAMES:                     # signature.png / photo.jpg
        return False
    if name.endswith(NP_FIRST_PAGE_SUFFIX):          # unstamped print copy
        return False
    return name.lower().endswith(".pdf")


def list_customer_documents(prefix: str, objects: list[dict]) -> list[dict]:
    """Logical document list (name/size) for the admin panel — no downloads."""
    docs = [
        {"name": o["name"], "size": o["size"], "type": "pdf"}
        for o in objects if _is_deliverable(prefix, o)
    ]
    by_key = {o["key"]: o for o in objects}
    if prefix + INSTALLATION_UPLOAD_KEY in by_key:
        docs.append({"name": INSTALLATION_OUT_NAME, "size": by_key[prefix + INSTALLATION_UPLOAD_KEY]["size"], "type": "pdf"})
    if prefix + DCR_UPLOAD_KEY in by_key:
        docs.append({"name": DCR_OUT_NAME, "size": by_key[prefix + DCR_UPLOAD_KEY]["size"], "type": "pdf"})
    return sorted(docs, key=lambda d: d["name"])


async def build_customer_bundle(prefix: str) -> list[tuple[str, bytes]]:
    """
    Assemble the final set of PDFs delivered to the customer:
      • generated docs (Annexure, Aadhar, WCR, etc.)
      • NP Agreement with the admin's stamped first page merged in front
      • admin-uploaded installation photo PDF and government DCR PDF
    Internal artifacts (signature, photo, unstamped first page) are excluded.
    """
    loop = asyncio.get_event_loop()
    objects = await loop.run_in_executor(None, storage.list_objects, prefix)
    keys = {o["key"] for o in objects}

    stamp_key = prefix + NP_STAMP_UPLOAD_KEY
    stamp_bytes = None
    if stamp_key in keys:
        stamp_bytes = await loop.run_in_executor(None, storage.download_bytes, stamp_key)

    bundle: list[tuple[str, bytes]] = []
    for o in sorted(objects, key=lambda o: o["name"]):
        if not _is_deliverable(prefix, o):
            continue
        data = await loop.run_in_executor(None, storage.download_bytes, o["key"])
        if o["name"].endswith(NP_AGREEMENT_SUFFIX) and stamp_bytes:
            data = merge_pdf_front(stamp_bytes, data)
        bundle.append((o["name"], data))

    for upload_key, out_name in ((prefix + INSTALLATION_UPLOAD_KEY, INSTALLATION_OUT_NAME),
                                 (prefix + DCR_UPLOAD_KEY, DCR_OUT_NAME)):
        if upload_key in keys:
            data = await loop.run_in_executor(None, storage.download_bytes, upload_key)
            bundle.append((out_name, data))

    return bundle
