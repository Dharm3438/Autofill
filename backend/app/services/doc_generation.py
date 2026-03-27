"""
Document generation service.
Fills DOCX templates with customer data and converts to PDF via docx2pdf (uses MS Word on Windows).
"""
import re
import asyncio
from pathlib import Path
from docx import Document
from docx2pdf import convert

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


def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", str(name)).strip()


def build_replacements(customer: dict) -> dict:
    replacements = {}
    for key, value in customer.items():
        if key.startswith("_") or value is None:
            continue
        replacements[f"${{{key}}}$"] = str(value) if value else ""
    return replacements


def process_paragraph(paragraph, replacements: dict):
    original = "".join(r.text for r in paragraph.runs)
    if not any(k in original for k in replacements):
        return
    for run in paragraph.runs:
        run.text = ""
    parts = re.split(f"({'|'.join(re.escape(k) for k in replacements)})", original)
    for part in parts:
        new_run = paragraph.add_run(replacements.get(part, part))
        if part in replacements:
            new_run.bold = True


def fill_template(template_path: Path, output_path: Path, replacements: dict):
    doc = Document(template_path)
    for para in doc.paragraphs:
        process_paragraph(para, replacements)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    process_paragraph(para, replacements)
    doc.save(output_path)


def convert_docx_to_pdf(docx_path: Path) -> bool:
    try:
        pdf_path = docx_path.with_suffix(".pdf")
        convert(str(docx_path), str(pdf_path))
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
    loop = asyncio.get_event_loop()

    for doc_type, template_file in TEMPLATES.items():
        template_path = TEMPLATE_DIR / template_file
        if not template_path.exists():
            print(f"Template not found: {template_path}")
            continue

        docx_path = output_dir / f"{safe_name}_{doc_type}.docx"

        await loop.run_in_executor(None, fill_template, template_path, docx_path, replacements)
        print(f"DOCX generated: {docx_path.name}")

        success = await loop.run_in_executor(None, convert_docx_to_pdf, docx_path)
        if success:
            print(f"PDF generated: {docx_path.stem}.pdf")
        else:
            print(f"PDF failed: {docx_path.stem}")

    return folder_name
