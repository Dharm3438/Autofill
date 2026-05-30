"""
Document generation service.
Fills DOCX templates with customer data and converts to PDF.
Windows: uses MS Word via docx2pdf. Linux: uses LibreOffice headless via subprocess.
"""
import re
import sys
import asyncio
import subprocess
from pathlib import Path
from docx import Document
from docx.shared import Inches

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "DOCS"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "generated_docs"

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
    customer_id = str(customer.get("_id", "unknown"))
    safe_name = sanitize(customer.get("CONSUMER_NAME", "customer"))
    folder_name = f"{customer_id}_{safe_name}"
    output_dir = OUTPUT_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    replacements = build_replacements(customer)

    # Auto-detect signature / photo from prior signing submission
    sig_file   = output_dir / "signature.png"
    photo_file = output_dir / "photo.jpg"
    images = {
        "signature": sig_file   if sig_file.exists()   else None,
        "photo":     photo_file if photo_file.exists() else None,
    }

    loop = asyncio.get_event_loop()

    for doc_type, template_file in TEMPLATES.items():
        template_path = TEMPLATE_DIR / template_file
        if not template_path.exists():
            print(f"Template not found: {template_path}")
            continue

        docx_path = output_dir / f"{safe_name}_{doc_type}.docx"

        await loop.run_in_executor(None, fill_template, template_path, docx_path, replacements, images)
        print(f"DOCX generated: {docx_path.name}")

        success = await loop.run_in_executor(None, convert_docx_to_pdf, docx_path)
        if success:
            print(f"PDF generated: {docx_path.stem}.pdf")
        else:
            print(f"PDF failed: {docx_path.stem}")

    return folder_name
