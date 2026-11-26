"""
Customer Details print sheet.

Fills the agency's one-page "Customer Details" PDF (backend/DOCS/
customer_details_template.pdf) with a customer's data so the admin can print
it. Values are written straight onto the original PDF, so the letterhead and
table layout stay exactly as designed (no DOCX round-trip, no LibreOffice).

Only the first table (customer details) and the "Total System Cost" row of
the amount table are filled. The installation checklist and payment rows are
left blank for writing by hand. Any blank field leaves its cell blank.
"""
import re
from pathlib import Path

import fitz  # PyMuPDF

from .formatting import document_value, fmt_number

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / "DOCS" / "customer_details_template.pdf"
)

FONT = "helv"          # built-in Helvetica, metric-compatible with the template's Arial
FONT_SIZE = 10         # same size as the template's row labels
MIN_FONT_SIZE = 8      # one-line values shrink down to this before wrapping
PAD = 5                # left padding inside a cell, matches the labels
TEXT_COLOR = (0, 0, 0)

# Cell geometry in PDF points, measured from the template (A4, 596 x 842).
# Columns of the "Particular" part of the details table.
_FULL = (219.8, 561.0)    # whole "Particular" cell
_LEFT = (219.8, 393.8)    # left half
_RIGHT = (393.8, 561.0)   # right half

# Row top/bottom per details-table row.
_ROWS = {
    "name":    (133.3, 155.8),
    "address": (155.8, 184.3),
    "mobile":  (184.3, 207.5),
    "email":   (207.5, 230.1),
    "aadhar":  (230.1, 252.5),
    "consumer_no": (252.5, 275.8),
    "load":    (275.8, 299.1),
    "inverter": (299.1, 321.5),
    "panel":   (321.5, 344.1),
    "subsidy_app_no": (344.1, 367.3),   # row 10: Subsidy Portal Application No / Date
    "app_no":  (367.3, 389.8),          # row 11: Application No / Date
}

# Right-half cells that already carry a printed label ("Dealer:", "Date:");
# the value is written just after where the label ends.
_DEALER_LABEL_END_X = 431.2
_DATE_LABEL_END_X = 422.9

# Amount table: "Total System Cost" row, amount column.
_TOTAL_COST_CELL = (70.5, 686.2, 306.8, 709.5)


def _s(customer: dict, key: str) -> str:
    """A field as printed (dates DD-MM-YYYY, money 1,50,000, kW 3.3)."""
    return document_value(key, customer.get(key))


def _required_load(customer: dict) -> str:
    """Solar Capacity with its unit: '3.3 kW'."""
    v = _s(customer, "SOLAR_CAPACITY")
    return f"{v} kW" if v else ""


def _inverter(customer: dict) -> str:
    """'GROWATT 3 kW'."""
    cap = _s(customer, "INVERTER_CAPACITY")
    parts = [_s(customer, "INVERTER_MAKE"), f"{cap} kW" if cap else ""]
    return " ".join(p for p in parts if p)


def _panel(customer: dict) -> str:
    """'WAAREE 540 W * 6 = 3.24 kW' — whatever parts are present."""
    company = _s(customer, "PANEL_COMPANY")
    watt = _s(customer, "PANEL_WATT")
    qty = _s(customer, "NO_OF_PANEL")

    spec = ""
    if watt:
        spec = f"{watt} W"
        if qty:
            spec += f" * {qty}"

    total_w = customer.get("TOTAL_PANEL_CAPACITY")
    if total_w:
        total = f"{fmt_number(total_w / 1000)} kW"
        spec = f"{spec} = {total}" if spec else total

    return " ".join(p for p in (company, spec) if p)


def _write(page: fitz.Page, x0: float, x1: float, row: tuple, text: str) -> None:
    """
    Write `text` vertically centred in the cell spanning x0..x1 / row.
    Shrinks the font to fit on one line; if it still doesn't fit at the
    minimum size, wraps inside the cell instead.
    """
    if not text:
        return
    y0, y1 = row
    width = (x1 - x0) - 2 * PAD

    size = FONT_SIZE
    while size > MIN_FONT_SIZE and fitz.get_text_length(text, FONT, size) > width:
        size -= 0.5

    if fitz.get_text_length(text, FONT, size) <= width:
        baseline = (y0 + y1) / 2 + size * 0.35
        page.insert_text((x0 + PAD, baseline), text,
                         fontname=FONT, fontsize=size, color=TEXT_COLOR)
        return

    # Too long for one line: wrap within the cell, using the largest size
    # that fits (insert_textbox writes nothing and returns < 0 if it doesn't).
    rect = fitz.Rect(x0 + PAD, y0 + 1, x1 - PAD, y1 - 1)
    size = FONT_SIZE - 1
    while size >= 5:
        if page.insert_textbox(rect, text, fontname=FONT, fontsize=size,
                               color=TEXT_COLOR) >= 0:
            return
        size -= 0.5


def build_customer_details_pdf(customer: dict) -> bytes:
    """Return the filled Customer Details sheet as PDF bytes."""
    doc = fitz.open(TEMPLATE_PATH)
    try:
        page = doc[0]
        R = _ROWS

        _write(page, *_FULL, R["name"], _s(customer, "CONSUMER_NAME"))
        _write(page, *_FULL, R["address"], _s(customer, "CONSUMER_ADDRESS"))
        _write(page, *_LEFT, R["mobile"], _s(customer, "CONSUMER_PHONE"))
        _write(page, _DEALER_LABEL_END_X - PAD + 3, _RIGHT[1], R["mobile"],
               _s(customer, "DEALER_NAME"))
        _write(page, *_FULL, R["email"], _s(customer, "CONSUMER_EMAIL"))
        _write(page, *_FULL, R["aadhar"], _s(customer, "CONSUMER_AADHAR"))
        _write(page, *_FULL, R["consumer_no"], _s(customer, "CONSUMER_NO"))
        _write(page, *_LEFT, R["load"], _required_load(customer))
        _write(page, *_LEFT, R["inverter"], _inverter(customer))
        _write(page, *_LEFT, R["panel"], _panel(customer))
        for row, no_key, date_key in (
            ("subsidy_app_no", "SUBSIDY_APP_NO", "SUBSIDY_APP_DATE"),
            ("app_no", "CONSUMER_APP_NO", "CONSUMER_APP_DATE"),
        ):
            _write(page, *_LEFT, R[row], _s(customer, no_key))
            _write(page, _DATE_LABEL_END_X - PAD + 3, _RIGHT[1], R[row],
                   _s(customer, date_key))

        x0, y0, x1, y1 = _TOTAL_COST_CELL
        cost = _s(customer, "SYSTEM_COST")
        _write(page, x0, x1, (y0, y1), f"Rs. {cost}" if cost else "")

        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()


def details_sheet_filename(customer: dict) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", _s(customer, "CONSUMER_NAME")).strip("_")
    return f"Customer_Details_{name or 'customer'}.pdf"
