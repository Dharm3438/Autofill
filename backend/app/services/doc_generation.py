"""
Document generation service.
Fills DOCX templates with customer data and converts to PDF.

PDF conversion uses LibreOffice headless on every platform (Windows, macOS,
Linux) so local output is byte-for-byte the same engine as production, where
the Docker image ships LibreOffice. There is intentionally no docx2pdf / MS
Word path — keeping a single conversion stack means "looks right locally"
also means "looks right in prod".
"""
import os
import re
import shutil
import asyncio
import tempfile
import subprocess
from functools import lru_cache
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
    # Kept under half the ~6.27in usable page width so FRONT and BACK sit
    # side by side on one line (at 3.0in each they overflowed and wrapped).
    "${AADHAR_FRONT}$":    ("aadhar_front", Inches(2.8)),
    "${AADHAR_BACK}$":     ("aadhar_back",  Inches(2.8)),
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


def _copy_run_format(src_run, dst_run):
    """Copy character-level formatting from src_run to dst_run (font name, size, italic, underline, color)."""
    sf, df = src_run.font, dst_run.font
    df.name      = sf.name
    df.size      = sf.size
    df.italic    = sf.italic
    df.underline = sf.underline
    if sf.color and sf.color.type is not None:
        try:
            df.color.rgb = sf.color.rgb
        except Exception:
            pass


def process_paragraph(paragraph, replacements: dict, images: dict):
    all_keys = list(replacements.keys()) + list(IMAGE_PLACEHOLDERS.keys())
    original = "".join(r.text for r in paragraph.runs)
    if not any(k in original for k in all_keys):
        return

    # Capture formatting from the first non-empty run before clearing all runs.
    # All runs in a template paragraph are typically uniform, so this covers the
    # whole paragraph (font name, size, color, etc.).
    fmt_run = next((r for r in paragraph.runs if r.text), None) or (paragraph.runs[0] if paragraph.runs else None)

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
                    if fmt_run:
                        _copy_run_format(fmt_run, new_run)
                    new_run.add_picture(str(img_path), width=width)
                except Exception as e:
                    print(f"Failed to embed image {img_path}: {e}")
            # else: leave blank — image not available yet
        elif part in replacements:
            new_run = paragraph.add_run(replacements[part])
            if fmt_run:
                _copy_run_format(fmt_run, new_run)
            new_run.bold = True  # filled values are always bolded
        else:
            new_run = paragraph.add_run(part)
            if fmt_run:
                _copy_run_format(fmt_run, new_run)


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


@lru_cache(maxsize=1)
def _find_soffice() -> str:
    """
    Locate the LibreOffice executable. Honours the LIBREOFFICE_PATH env var,
    then falls back to PATH, then to the usual per-OS install locations.
    Raises RuntimeError with install guidance if LibreOffice is missing.
    """
    override = os.environ.get("LIBREOFFICE_PATH")
    if override and Path(override).exists():
        return override

    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    candidates = [
        # Windows
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        # macOS
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        # Linux (when not on PATH)
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
    ]
    for path in candidates:
        if Path(path).exists():
            return path

    raise RuntimeError(
        "LibreOffice not found. Install it so DOCX→PDF works the same as prod:\n"
        "  Windows: winget install --id TheDocumentFoundation.LibreOffice\n"
        "  macOS:   brew install --cask libreoffice\n"
        "  Linux:   apt-get install libreoffice\n"
        "Or set LIBREOFFICE_PATH to the soffice executable."
    )


def convert_docx_to_pdf(docx_path: Path) -> bool:
    """
    Convert a single DOCX to a PDF beside it using LibreOffice headless.

    Thin wrapper over convert_docx_batch — kept for single-file callers
    (e.g. the docgen_test.py harness). For generating a customer's full set,
    use convert_docx_batch so LibreOffice only starts up once.
    """
    produced = convert_docx_batch([docx_path], docx_path.parent)
    return docx_path.with_suffix(".pdf") in produced


def convert_docx_batch(docx_paths: list[Path], outdir: Path) -> set[Path]:
    """
    Convert many DOCX files to PDF in a single LibreOffice invocation.

    LibreOffice's ~1–2s startup is the expensive part, so converting a whole
    customer's documents in one `soffice` call instead of one-per-file is the
    dominant doc-gen speedup. If one document is malformed LibreOffice still
    converts the rest, so we report success per-file by checking which PDFs
    actually landed in `outdir`.

    A throwaway user-profile dir is passed via -env:UserInstallation so the
    conversion never collides with (or hangs behind) a LibreOffice window the
    user may already have open, and so concurrent batches stay isolated.

    Returns the set of PDF paths that were produced.
    """
    docx_paths = [p for p in docx_paths if p.exists()]
    if not docx_paths:
        return set()

    expected = {outdir / (p.stem + ".pdf") for p in docx_paths}
    profile_dir = Path(tempfile.mkdtemp(prefix="lo_profile_"))
    profile_uri = profile_dir.as_uri()
    # One LibreOffice startup serves the whole batch; scale the timeout with the
    # number of files (with generous headroom) rather than the old flat 120s.
    timeout = min(120 + 30 * len(docx_paths), 600)
    try:
        soffice = _find_soffice()
        result = subprocess.run(
            [soffice, "--headless", "--nologo", "--nofirststartwizard",
             f"-env:UserInstallation={profile_uri}",
             "--convert-to", "pdf", "--outdir", str(outdir),
             *[str(p) for p in docx_paths]],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            print(f"LibreOffice batch error: {result.stderr.strip() or result.stdout.strip()}")
    except subprocess.TimeoutExpired:
        print(f"PDF batch conversion timed out ({len(docx_paths)} files)")
    except Exception as e:
        print(f"PDF batch conversion failed: {e}")
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    produced = {p for p in expected if p.exists()}
    for missing in expected - produced:
        print(f"PDF failed: {missing.stem}")
    return produced


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

        # Phase 1 — fill every template's DOCX.
        docx_paths: list[Path] = []
        for doc_type, template_file in TEMPLATES.items():
            template_path = TEMPLATE_DIR / template_file
            if not template_path.exists():
                print(f"Template not found: {template_path}")
                continue
            docx_path = work_dir / f"{safe_name}_{doc_type}.docx"
            await loop.run_in_executor(None, fill_template, template_path, docx_path, replacements, images)
            docx_paths.append(docx_path)

        # Phase 2 — convert them all to PDF in a single LibreOffice startup.
        produced = await loop.run_in_executor(None, convert_docx_batch, docx_paths, work_dir)

        # Phase 3 — upload the produced PDFs to R2 in parallel (independent I/O).
        async def _upload(pdf_path: Path):
            await loop.run_in_executor(
                None, storage.upload_file, pdf_path, prefix + pdf_path.name, "application/pdf"
            )
            print(f"Uploaded to R2: {prefix + pdf_path.name}")

        await asyncio.gather(*(_upload(p) for p in sorted(produced)))
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


# Friendly, customer-facing labels for the documents shown on the signing page.
# Keyed by the generated doc_type (the suffix of the R2 object name).
SIGNING_DOC_LABELS = {
    "Annexure_1":           "Annexure-1 — Solar Installation Declaration",
    "Aadhar":               "Aadhaar Declaration",
    "WCR":                  "Work Completion Report",
    "Annexure_3":           "Annexure-3 — Net Metering",
    "NP_Agreement":         "Net-Metering Agreement",
    "Meter_testing_letter": "Meter Testing Letter",
}


def signing_document_list(prefix: str, objects: list[dict], customer: dict) -> list[dict]:
    """
    Ordered list of documents shown to the customer on the signing page for
    review-before-consent. Mirrors `build_customer_bundle` so what they review
    is exactly what gets delivered (minus the signature/photo, which are added
    after they sign). Each item carries a stable `key`, a friendly `label`, and
    the internal fetch info (`r2_key`, `merge_stamp`) used by
    `fetch_signing_document`.
    """
    safe_name = sanitize(customer.get("CONSUMER_NAME", "customer"))
    keys = {o["key"]: o for o in objects}
    items: list[dict] = []

    # Generated deliverables, sorted by name for a stable, deterministic order.
    for o in sorted((o for o in objects if _is_deliverable(prefix, o)), key=lambda o: o["name"]):
        name = o["name"]
        doc_type = name[len(safe_name) + 1:-4] if name.startswith(safe_name + "_") else name[:-4]
        label = SIGNING_DOC_LABELS.get(doc_type) or doc_type.replace("_", " ")
        items.append({
            "label": label,
            "r2_key": o["key"],
            "merge_stamp": name.endswith(NP_AGREEMENT_SUFFIX),
        })

    # Admin uploads delivered alongside the generated docs.
    if prefix + INSTALLATION_UPLOAD_KEY in keys:
        items.append({"label": "Installation Photo", "r2_key": prefix + INSTALLATION_UPLOAD_KEY, "merge_stamp": False})
    if prefix + DCR_UPLOAD_KEY in keys:
        items.append({"label": "DCR Declaration", "r2_key": prefix + DCR_UPLOAD_KEY, "merge_stamp": False})

    for i, item in enumerate(items):
        item["key"] = str(i)
    return items


async def fetch_signing_document(prefix: str, customer: dict, key: str) -> tuple[str, bytes] | None:
    """
    Fetch a single signing-page document's PDF bytes by its stable `key`.
    Applies the same stamped-first-page merge as the delivered bundle so the
    NP Agreement the customer reviews matches the final document. Returns
    (label, pdf_bytes) or None if the key doesn't resolve.
    """
    loop = asyncio.get_event_loop()
    objects = await loop.run_in_executor(None, storage.list_objects, prefix)
    item = next((it for it in signing_document_list(prefix, objects, customer) if it["key"] == key), None)
    if not item:
        return None

    data = await loop.run_in_executor(None, storage.download_bytes, item["r2_key"])
    if item["merge_stamp"]:
        stamp_key = prefix + NP_STAMP_UPLOAD_KEY
        if await loop.run_in_executor(None, storage.object_exists, stamp_key):
            stamp_bytes = await loop.run_in_executor(None, storage.download_bytes, stamp_key)
            data = merge_pdf_front(stamp_bytes, data)
    return item["label"], data


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
