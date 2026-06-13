"""
Standalone document-generation test harness.

Fills every DOCX template in DOCS/ with sample data and converts each to PDF
using the *exact same* fill + LibreOffice pipeline the production app uses
(app.services.doc_generation). No MongoDB, R2, or running server required —
just edit a template and run this to see how the final DOCX/PDF look.

Usage (from the backend/ directory, with the venv active):

    python docgen_test.py                # generate all templates -> test_output/
    python docgen_test.py --open         # ...and open the output folder
    python docgen_test.py --no-images    # skip the sample signature/photo images
    python docgen_test.py --docx-only    # fill DOCX but skip PDF conversion
    python docgen_test.py --only WCR Annexure_3   # only these template keys

Edit SAMPLE_CUSTOMER below to change the values that get filled in.
"""
import os
import sys
import time
import shutil
import argparse
import subprocess
from pathlib import Path

# The Windows console defaults to cp1252 and chokes on the ✓/✗/→ glyphs below.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Make config load even without a real .env ────────────────────────────────
# importing doc_generation pulls in core.config (Settings), which requires a
# few env vars. Provide harmless defaults so this script runs on a bare
# checkout. Real values in .env, if present, still win (set via setdefault).
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used")

# Ensure "app" is importable when run from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services import doc_generation as dg  # noqa: E402

# ── Sample data — every placeholder field, with realistic-looking values ─────
# Date fields use DD-MM-YYYY, matching how the app formats them before filling.
SAMPLE_CUSTOMER = {
    "CONSUMER_NAME":            "Ramesh Kumar Patel",
    "CONSUMER_ADDRESS":         "12 Sunrise Society, Near Water Tank, Maninagar, Ahmedabad - 380008",
    "CONSUMER_PHONE":           "9876543210",
    "CONSUMER_EMAIL":           "ramesh.patel@example.com",
    "CONSUMER_AADHAR":          "1234 5678 9012",
    "CONSUMER_NO":              "39201234567",
    "SANCTIONED_CAPACITY":      "5 kW",
    "CONSUMER_APP_DATE":        "15-01-2026",
    "CONSUMER_APP_NO":          "APP-2026-004521",
    "SOLAR_CAPACITY":           "5.4 kW",
    "INVERTER_MAKE":            "Growatt",
    "INVERTER_CAPACITY":        "5 kW",
    "INVERTER_GURANTEE":        "10 Years",
    "INVERTER_SR_NO":           "GW5K-2026-INV-88231",
    "PANEL_COMPANY":            "Waaree Energies",
    "PANEL_WATT":               "540 W",
    "NO_OF_PANEL":              "10",
    "TOTAL_PANEL_CAPACITY":     "5.4 kW",
    "PANEL_SR_NO":              "WP540-0001, WP540-0002, WP540-0003, WP540-0004, WP540-0005, "
                                "WP540-0006, WP540-0007, WP540-0008, WP540-0009, WP540-0010",
    "CELL_MANUFACTURER":        "Waaree",
    "PANEL_GURANTEE":           "25 Years",
    "INSTALLATION_DATE":        "20-02-2026",
    "INSTALLATION_CITY":        "Ahmedabad",
    "INSTALLATION_DISTRICT":    "Ahmedabad",
    "DISCOM_REGISTERED_OFFICE": "Torrent Power Ltd, Ahmedabad",
    "SYSTEM_COST":              "2,75,000",
    "METER_TESTING_DATE":       "05-03-2026",
    "METER_RECIPT_NO":          "MTR-RCPT-2026-7781",
    "GENERATION_METER_MAKE":    "Secure Meters",
    "GENERATION_METER_NO":      "GM-9988776655",
}

OUTPUT_DIR = Path(__file__).resolve().parent / "test_output"


def make_sample_images(dest: Path) -> dict:
    """
    Create simple placeholder images so the ${CUSTOMER_SIGN}$ / ${CUSTOMER_PHOTO}$
    / ${AADHAR_*}$ placeholders render something. Returns the images dict that
    fill_template expects: {"signature": Path|None, "photo": ..., ...}.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  (Pillow not installed — skipping sample images)")
        return {k: None for k in ("signature", "photo", "aadhar_front", "aadhar_back")}

    dest.mkdir(parents=True, exist_ok=True)

    def _placeholder(name: str, size, color, label):
        path = dest / name
        img = Image.new("RGB", size, color)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(2, 2), (size[0] - 3, size[1] - 3)], outline=(80, 80, 80), width=2)
        draw.text((10, size[1] // 2 - 6), label, fill=(40, 40, 40))
        img.save(path)
        return path

    return {
        "signature":    _placeholder("signature.png", (320, 120), (245, 245, 245), "SAMPLE SIGNATURE"),
        "photo":        _placeholder("photo.jpg",      (300, 300), (230, 240, 230), "SAMPLE PHOTO"),
        "aadhar_front": _placeholder("aadhar_front.jpg", (480, 300), (235, 235, 245), "AADHAAR FRONT"),
        "aadhar_back":  _placeholder("aadhar_back.jpg",  (480, 300), (245, 235, 235), "AADHAAR BACK"),
    }


def open_folder(path: Path):
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
    except Exception as e:
        print(f"  (couldn't open folder automatically: {e})")


def main():
    parser = argparse.ArgumentParser(description="Test DOCX→PDF generation locally.")
    parser.add_argument("--only", nargs="+", metavar="KEY",
                        help=f"Only generate these template keys. Available: {', '.join(dg.TEMPLATES)}")
    parser.add_argument("--docx-only", action="store_true", help="Fill DOCX but skip PDF conversion.")
    parser.add_argument("--no-images", action="store_true", help="Don't embed sample signature/photo images.")
    parser.add_argument("--keep", action="store_true", help="Keep previous output (don't wipe test_output/).")
    parser.add_argument("--open", action="store_true", help="Open the output folder when done.")
    args = parser.parse_args()

    templates = dict(dg.TEMPLATES)
    if args.only:
        unknown = [k for k in args.only if k not in templates]
        if unknown:
            print(f"Unknown template key(s): {', '.join(unknown)}")
            print(f"Available: {', '.join(templates)}")
            return 1
        templates = {k: templates[k] for k in args.only}

    # Confirm LibreOffice is reachable up front (clearer than a per-file failure).
    if not args.docx_only:
        try:
            print(f"LibreOffice: {dg._find_soffice()}")
        except RuntimeError as e:
            print(f"\n{e}\n")
            return 1

    if OUTPUT_DIR.exists() and not args.keep:
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

    # DOCX and PDF land in separate folders so it's easy to scan one or the other.
    docx_dir = OUTPUT_DIR / "docx"
    pdf_dir = OUTPUT_DIR / "pdf"
    docx_dir.mkdir(parents=True, exist_ok=True)
    if not args.docx_only:
        pdf_dir.mkdir(parents=True, exist_ok=True)

    images = {k: None for k in ("signature", "photo", "aadhar_front", "aadhar_back")}
    if not args.no_images:
        images = make_sample_images(OUTPUT_DIR / "_sample_images")

    replacements = dg.build_replacements(SAMPLE_CUSTOMER)
    safe_name = dg.sanitize(SAMPLE_CUSTOMER["CONSUMER_NAME"])

    print(f"\nTemplate dir : {dg.TEMPLATE_DIR}")
    print(f"DOCX dir     : {docx_dir}")
    print(f"PDF dir      : {pdf_dir}")
    print(f"Templates    : {len(templates)}\n")

    ok = fail = 0
    t0 = time.perf_counter()
    for doc_type, template_file in templates.items():
        template_path = dg.TEMPLATE_DIR / template_file
        if not template_path.exists():
            print(f"  ✗  [{doc_type}] template missing: {template_path.name}")
            fail += 1
            continue

        docx_path = docx_dir / f"{safe_name}_{doc_type}.docx"
        try:
            dg.fill_template(template_path, docx_path, replacements, images)
        except Exception as e:
            print(f"  ✗  [{doc_type}] DOCX fill failed: {e}")
            fail += 1
            continue

        if args.docx_only:
            print(f"  ✓  [{doc_type}] DOCX → docx/{docx_path.name}")
            ok += 1
            continue

        # convert_docx_to_pdf writes the PDF beside the DOCX; move it into pdf/.
        t = time.perf_counter()
        success = dg.convert_docx_to_pdf(docx_path)
        dt = time.perf_counter() - t
        produced = docx_path.with_suffix(".pdf")
        if success and produced.exists():
            final_pdf = pdf_dir / produced.name
            shutil.move(str(produced), str(final_pdf))
            print(f"  ✓  [{doc_type}] PDF  → pdf/{final_pdf.name}  ({dt:.1f}s)")
            ok += 1
        else:
            print(f"  ✗  [{doc_type}] PDF conversion failed")
            fail += 1

    elapsed = time.perf_counter() - t0
    print(f"\n{'─' * 50}")
    print(f"Done: {ok} ok, {fail} failed in {elapsed:.1f}s")
    print(f"Open: {OUTPUT_DIR}")

    if args.open:
        open_folder(OUTPUT_DIR)

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
