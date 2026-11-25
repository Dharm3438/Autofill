"""
Customer Details sheet tests. Run from backend/:

    venv\\Scripts\\python -m unittest discover -s tests -v

Row 10 of the sheet is the Subsidy Portal Application No/Date (SUBSIDY_APP_*),
row 11 the plain Application No/Date (CONSUMER_APP_*). Documents keep using
CONSUMER_APP_*.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz  # noqa: E402

from app.services.customer_sheet import build_customer_details_pdf  # noqa: E402
from app.services.doc_generation import required_fields_by_document  # noqa: E402


def _row_text(pdf: bytes, label: str) -> str:
    """Text on the same line as the row whose label starts with `label`."""
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    hits = page.search_for(label)
    if not hits:
        return ""
    mid = (hits[0].y0 + hits[0].y1) / 2
    words = [(w[0], w[4]) for w in page.get_text("words")
             if abs((w[1] + w[3]) / 2 - mid) < 5]   # same table row
    return " ".join(w for _, w in sorted(words))


class CustomerSheetTest(unittest.TestCase):
    def test_both_application_rows_are_filled(self):
        pdf = build_customer_details_pdf({
            "CONSUMER_NAME": "Test",
            "SUBSIDY_APP_NO": "NP-MHMS25-1234",
            "SUBSIDY_APP_DATE": "2026-11-20",
            "CONSUMER_APP_NO": "APP-5678",
            "CONSUMER_APP_DATE": "2026-11-22",
        })
        subsidy = _row_text(pdf, "Subsidy Portal Application No")
        self.assertIn("NP-MHMS25-1234", subsidy)
        self.assertIn("20-11-2026", subsidy)
        self.assertNotIn("APP-5678", subsidy)

        app = _row_text(pdf, "11 Application No")
        self.assertIn("APP-5678", app)
        self.assertIn("22-11-2026", app)

    def test_documents_never_use_subsidy_fields(self):
        for doc_type, fields in required_fields_by_document().items():
            self.assertFalse({"SUBSIDY_APP_NO", "SUBSIDY_APP_DATE"} & set(fields), doc_type)


if __name__ == "__main__":
    unittest.main()
