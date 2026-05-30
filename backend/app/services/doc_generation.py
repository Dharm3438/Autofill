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
from docx import Document
from docx.shared import Inches

from . import storage

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "DOCS"

SIGNATURE_KEY = "signature.png"
PHOTO_KEY = "photo.jpg"

TEMPLATES = {
    "Annexure_1":           "TEMPELATE_Annexure.docx",
    "Aadhar":               "Aadhar.docx",
    "WCR":                  "WCR.docx",
    "Annexure_3":           "Annexure-3-Net-Metering.docx",
    "NP_Agreement":         "np_agreement.docx",
    "Meter_testing_letter": "Meter Testing Letter.docx",
    "DCR":                  "DCR.docx",
}

# placeholder -> (image-key, render width)
IMAGE_PLACEHOLDERS = {
    "${CUSTOMER_SIGN}$":  ("signature", Inches(2.5)),
    "${CUSTOMER_PHOTO}$": ("photo",     Inches(2.5)),
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
        # Pull signature / photo down from R2 (saved during signing) so they get embedded
        images = {}
        for img_key, fname in (("signature", SIGNATURE_KEY), ("photo", PHOTO_KEY)):
            r2_key = prefix + fname
            local = work_dir / fname
            if await loop.run_in_executor(None, storage.object_exists, r2_key):
                data = await loop.run_in_executor(None, storage.download_bytes, r2_key)
                local.write_bytes(data)
                images[img_key] = local
            else:
                images[img_key] = None

        # Remove any stale PDFs from a previous generation before uploading fresh ones
        stale = [o["key"] for o in await loop.run_in_executor(None, storage.list_objects, prefix)
                 if o["key"].lower().endswith(".pdf")]
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
