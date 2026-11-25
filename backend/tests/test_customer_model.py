"""
Typed customer data: validation, normalisation, derived fields, document
formatting and customer-list sorting. Run from backend/:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

from pydantic import ValidationError  # noqa: E402

from app.models.customer import CustomerCreate, derived_fields, missing_required_fields  # noqa: E402
from app.services.doc_generation import build_replacements  # noqa: E402
from app.services.formatting import fmt_date, fmt_inr, fmt_number  # noqa: E402

try:
    import mongomock
except ImportError:  # pragma: no cover
    mongomock = None


def errors(**fields):
    try:
        CustomerCreate(**fields)
    except ValidationError as e:
        return {err["loc"][0]: err["type"] for err in e.errors()}
    return {}


class ValidationTest(unittest.TestCase):
    def test_numbers_are_stored_as_numbers(self):
        c = CustomerCreate(SYSTEM_COST="150000", SOLAR_CAPACITY="3.30", PANEL_WATT="540",
                           NO_OF_PANEL="6", INVERTER_CAPACITY="3.3").to_store()
        self.assertEqual((c["SYSTEM_COST"], c["SOLAR_CAPACITY"], c["PANEL_WATT"], c["NO_OF_PANEL"]),
                         (150000, 3.3, 540, 6))
        self.assertIsInstance(c["SYSTEM_COST"], int)
        self.assertEqual(c["INVERTER_CAPACITY"], 3.3)

    def test_bad_numbers_rejected(self):
        self.assertIn("SYSTEM_COST", errors(SYSTEM_COST="1,50,000"))
        self.assertIn("SYSTEM_COST", errors(SYSTEM_COST=1500.5))   # no paise
        self.assertIn("SYSTEM_COST", errors(SYSTEM_COST=-1))
        self.assertIn("NO_OF_PANEL", errors(NO_OF_PANEL=0))
        self.assertIn("SOLAR_CAPACITY", errors(SOLAR_CAPACITY="3 kW"))

    def test_blank_is_null(self):
        c = CustomerCreate(SYSTEM_COST="", CONSUMER_EMAIL="", CONSUMER_APP_DATE="  ",
                           INSTALLATION_CITY=" ").to_store()
        self.assertIsNone(c["SYSTEM_COST"])
        self.assertIsNone(c["CONSUMER_EMAIL"])
        self.assertIsNone(c["CONSUMER_APP_DATE"])
        self.assertIsNone(c["INSTALLATION_CITY"])

    def test_dates_validated_and_iso(self):
        self.assertEqual(CustomerCreate(CONSUMER_APP_DATE="2026-03-05").to_store()["CONSUMER_APP_DATE"],
                         "2026-03-05")
        self.assertIn("CONSUMER_APP_DATE", errors(CONSUMER_APP_DATE="05-03-2026"))
        self.assertIn("METER_TESTING_DATE", errors(METER_TESTING_DATE="2026-02-30"))

    def test_ids_normalised(self):
        c = CustomerCreate(CONSUMER_PHONE="+91 98765-43210", CONSUMER_AADHAR="1234 5678 9012",
                           CONSUMER_NO=" 0123 4567 ").to_store()
        self.assertEqual((c["CONSUMER_PHONE"], c["CONSUMER_AADHAR"], c["CONSUMER_NO"]),
                         ("9876543210", "123456789012", "01234567"))
        self.assertIn("CONSUMER_PHONE", errors(CONSUMER_PHONE="12345"))
        self.assertIn("CONSUMER_AADHAR", errors(CONSUMER_AADHAR="1234"))

    def test_choices_must_be_in_catalog(self):
        self.assertIn("DEALER_NAME", errors(DEALER_NAME="Someone New"))
        self.assertIn("INVERTER_MAKE", errors(INVERTER_MAKE="utl"))
        self.assertIn("PANEL_WATT", errors(PANEL_WATT=541))
        self.assertIn("INVERTER_CAPACITY", errors(INVERTER_CAPACITY=7))
        self.assertEqual(errors(DEALER_NAME="Office", INVERTER_MAKE="UTL", PANEL_COMPANY="TATA",
                                PANEL_WATT=540, INVERTER_CAPACITY=3.3), {})

    def test_serials_comma_separated(self):
        c = CustomerCreate(PANEL_SR_NO="A1,A2 ,\n A3,, ").to_store()
        self.assertEqual(c["PANEL_SR_NO"], "A1, A2, A3")

    def test_update_keeps_only_sent_fields(self):
        self.assertEqual(CustomerCreate(SYSTEM_COST=5).to_store(only_sent=True), {"SYSTEM_COST": 5})
        # Sent blank → explicit null, so a required field can't be blanked.
        sent = CustomerCreate(SYSTEM_COST="").to_store(only_sent=True)
        self.assertEqual(missing_required_fields(sent, partial=True), ["System Cost"])

    def test_derived_fields(self):
        d = derived_fields({"PANEL_WATT": 540, "NO_OF_PANEL": 6, "INVERTER_MAKE": "Polycab",
                            "PANEL_COMPANY": "UTL"})
        self.assertEqual(d, {"TOTAL_PANEL_CAPACITY": 3240, "INVERTER_GUARANTEE": 8, "PANEL_GUARANTEE": 27})
        self.assertIsNone(derived_fields({"PANEL_WATT": 540})["TOTAL_PANEL_CAPACITY"])


class FormattingTest(unittest.TestCase):
    def test_formatters(self):
        self.assertEqual(fmt_inr(150000), "1,50,000")
        self.assertEqual(fmt_inr(12345678), "1,23,45,678")
        self.assertEqual(fmt_inr(999), "999")
        self.assertEqual(fmt_number(5.0), "5")
        self.assertEqual(fmt_number(3.30), "3.3")
        self.assertEqual(fmt_date("2026-03-05"), "05-03-2026")

    def test_document_replacements(self):
        r = build_replacements({
            "CONSUMER_APP_DATE": "2026-03-05", "INVERTER_CAPACITY": 5.0,
            "AGREEMENT_SYSTEM_COST": 240000, "PANEL_GUARANTEE": 30, "METER_TESTING_DATE": None,
            "CONSUMER_NAME": "Ramesh", "installation_steps": [{"key": "x"}],
        })
        self.assertEqual(r["${CONSUMER_APP_DATE}$"], "05-03-2026")
        self.assertEqual(r["${INVERTER_CAPACITY}$"], "5")      # template adds "KW"
        self.assertEqual(r["${AGREEMENT_SYSTEM_COST}$"], "2,40,000")
        self.assertEqual(r["${PANEL_GUARANTEE}$"], "30 YEAR")
        self.assertNotIn("${METER_TESTING_DATE}$", r)
        self.assertNotIn("${installation_steps}$", r)


class ValidationMessageTest(unittest.TestCase):
    def test_one_readable_sentence(self):
        try:
            from fastapi.testclient import TestClient
        except Exception:  # pragma: no cover - needs httpx
            self.skipTest("fastapi.testclient needs httpx")
        from app.main import app
        from app.core.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {"_id": "u", "roles": ["admin"]}
        try:
            res = TestClient(app).post("/api/customers", json={"CONSUMER_PHONE": "12", "SYSTEM_COST": "1,50,000"})
        finally:
            app.dependency_overrides.clear()
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["detail"],
                         "Phone must be a 10-digit mobile number; System Cost must be a whole number")


@unittest.skipIf(mongomock is None, "mongomock not installed")
class ListSortTest(unittest.TestCase):
    """The customer list sorts on the stored numbers/dates themselves."""

    def setUp(self):
        from app.core import database
        from app.routers import customers

        raw = mongomock.MongoClient().db

        class Cursor:
            def __init__(self, cur):
                self.cur = cur

            def sort(self, spec):
                self.cur = self.cur.sort(spec)
                return self

            def skip(self, n):
                self.cur = self.cur.skip(n)
                return self

            def limit(self, n):
                self.cur = self.cur.limit(n)
                return self

            def collation(self, _c):
                return self  # mongomock ignores collation; names below differ in more than case

            def __aiter__(self):
                self.it = iter(self.cur)
                return self

            async def __anext__(self):
                try:
                    return next(self.it)
                except StopIteration:
                    raise StopAsyncIteration

        class Coll:
            def find(self, q):
                return Cursor(raw.customers.find(q))

            async def count_documents(self, q):
                return raw.customers.count_documents(q)

        class DB:
            customers = Coll()

        database.db = DB()
        self.customers = customers
        for name, cost, app_date, cap, created in [
            ("Bharat", 200000, "2026-02-01", 5.0, "2026-01-02"),
            ("Amit", 99000, "2026-03-01", 3.3, "2026-01-03"),
            ("Chetan", 1500000, "2026-01-01", 10.0, "2026-01-01"),
        ]:
            raw.customers.insert_one({"CONSUMER_NAME": name, "SYSTEM_COST": cost, "CONSUMER_APP_DATE": app_date,
                                      "SOLAR_CAPACITY": cap, "created_at": created})

    def names(self, sort):
        from test_permissions import run, make_user
        res = run(self.customers.list_customers(search="", page=1, limit=10, sort=sort, user=make_user("admin")))
        return [c["CONSUMER_NAME"] for c in res["data"]]

    def test_sorts(self):
        # Numeric, not text order: "1500000" < "200000" < "99000" as strings.
        self.assertEqual(self.names("cost_desc"), ["Chetan", "Bharat", "Amit"])
        self.assertEqual(self.names("cost_asc"), ["Amit", "Bharat", "Chetan"])
        self.assertEqual(self.names("app_date_desc"), ["Amit", "Bharat", "Chetan"])
        self.assertEqual(self.names("capacity_desc"), ["Chetan", "Bharat", "Amit"])
        self.assertEqual(self.names("name"), ["Amit", "Bharat", "Chetan"])
        self.assertEqual(self.names("newest"), ["Amit", "Bharat", "Chetan"])

    def test_unknown_sort(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            self.names("bogus")


if __name__ == "__main__":
    unittest.main()
