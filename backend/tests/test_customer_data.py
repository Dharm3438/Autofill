"""
Backup / wipe / restore tool (scripts/customer_data.py). Run from backend/:

    python -m unittest discover -s tests

Uses mongomock (an in-memory MongoDB); skipped if it isn't installed.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

try:
    import mongomock
except ImportError:  # pragma: no cover
    mongomock = None

from bson import ObjectId  # noqa: E402

import customer_data as cd  # noqa: E402
from app.core import database  # noqa: E402
from test_permissions import run, seeded_db  # noqa: E402

KEYS = ["structure", "inverter", "panels"]

# A customer as the app stored it before typed fields (free text everywhere).
LEGACY = {
    "CONSUMER_NAME": "Ramesh Patil", "CONSUMER_ADDRESS": "1 Main Road",
    "CONSUMER_PHONE": "98765 43210", "CONSUMER_AADHAR": "1234 5678 9012", "CONSUMER_EMAIL": "",
    "CONSUMER_NO": "0123 456", "DEALER_NAME": "Office", "CONSUMER_APP_NO": "APP-1",
    "CONSUMER_APP_DATE": "15-03-2026", "SOLAR_CAPACITY": "3.3 kW", "SANCTIONED_CAPACITY": "3",
    "INVERTER_MAKE": "Polycab", "INVERTER_CAPACITY": "3.3 kW", "INVERTER_GURANTEE": "8 YEAR",
    "PANEL_COMPANY": "WAAREE", "PANEL_WATT": "540", "NO_OF_PANEL": "6", "TOTAL_PANEL_CAPACITY": "3240",
    "PANEL_GURANTEE": "30 YEAR", "SYSTEM_COST": "1,50,000", "AGREEMENT_SYSTEM_COST": "₹1,20,000",
    "METER_RECIPT_NO": "R-77", "METER_TESTING_DATE": "2026-04-01",
    "received_payments": [{"amount": 50000.0, "date": "2026-03-20"}],
    "payment_status": "due", "paid_percent": 33.3,
    "installation_steps": [{"key": "inverter", "status": "done", "completed_date": "2026-04-10"}],
    "doc_status": "complete", "signing_status": "signed", "created_by": "u1",
    "created_at": "2026-03-15T10:00:00+00:00",
}


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def customer_prefix(self, cid):
        return f"customers/{cid}/"

    def list_objects(self, prefix):
        return [{"key": k} for k in self.objects if k.startswith(prefix)]

    def download_bytes(self, key):
        return self.objects[key]

    def upload_bytes(self, data, key, content_type=None):
        self.objects[key] = data


def catalog_from_seed():
    """Mongo catalog_items as seeded on startup (copied out of the fake DB)."""
    db = seeded_db()
    return list(db.catalog_items.docs)


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.catalog = cd.Catalog(catalog_from_seed())

    def test_old_text_becomes_typed(self):
        doc, issues = cd.convert_customer(dict(LEGACY, _id=ObjectId()), self.catalog)
        self.assertEqual(issues, {})
        self.assertEqual((doc["SYSTEM_COST"], doc["AGREEMENT_SYSTEM_COST"]), (150000, 120000))
        self.assertEqual((doc["SOLAR_CAPACITY"], doc["SANCTIONED_CAPACITY"], doc["INVERTER_CAPACITY"]),
                         (3.3, 3.0, 3.3))
        self.assertEqual((doc["PANEL_WATT"], doc["NO_OF_PANEL"], doc["TOTAL_PANEL_CAPACITY"]), (540, 6, 3240))
        self.assertEqual(doc["CONSUMER_APP_DATE"], "2026-03-15")
        self.assertEqual((doc["CONSUMER_PHONE"], doc["CONSUMER_AADHAR"], doc["CONSUMER_NO"]),
                         ("9876543210", "123456789012", "0123456"))
        self.assertIsNone(doc["CONSUMER_EMAIL"])
        self.assertEqual((doc["INVERTER_GUARANTEE"], doc["PANEL_GUARANTEE"]), (8, 30))
        self.assertEqual(doc["METER_RECEIPT_NO"], "R-77")
        self.assertEqual(doc["received_payments"], [{"amount": 50000, "date": "2026-03-20"}])
        self.assertEqual(doc["INSTALLATION_DATE"], "2026-04-10")
        for gone in ("INVERTER_GURANTEE", "METER_RECIPT_NO", "payment_status", "paid_percent"):
            self.assertNotIn(gone, doc)
        # Status / ownership fields carried over untouched.
        self.assertEqual((doc["doc_status"], doc["created_by"]), ("complete", "u1"))

    def test_legacy_single_payment(self):
        raw = dict(LEGACY, _id=ObjectId(), received_payments=None, received_payment="25,000")
        doc, _ = cd.convert_customer(raw, self.catalog)
        self.assertEqual(doc["received_payments"], [{"amount": 25000, "date": None}])
        self.assertNotIn("received_payment", doc)

    def test_bad_values_blanked_but_kept(self):
        raw = dict(LEGACY, _id=ObjectId(), CONSUMER_AADHAR="1234", SYSTEM_COST="TBD",
                   DEALER_NAME="Old Dealer")
        doc, issues = cd.convert_customer(raw, self.catalog)
        self.assertIsNone(doc["CONSUMER_AADHAR"])
        self.assertIsNone(doc["SYSTEM_COST"])
        self.assertEqual(doc["import_issues"], {"CONSUMER_AADHAR": "1234", "SYSTEM_COST": "TBD"})
        # A dealer no longer in the list is kept, just reported.
        self.assertEqual(doc["DEALER_NAME"], "Old Dealer")
        self.assertEqual(issues["not_in_catalog"], {"DEALER_NAME": "Old Dealer"})


@unittest.skipIf(mongomock is None, "mongomock not installed")
class RoundTripTest(unittest.TestCase):
    def setUp(self):
        self.db = mongomock.MongoClient().db
        self.db.catalog_items.insert_many(catalog_from_seed())
        self.ids = [ObjectId(), ObjectId()]
        self.db.customers.insert_many([
            dict(LEGACY, _id=self.ids[0]),
            dict(LEGACY, _id=self.ids[1], CONSUMER_NAME="Suresh", CONSUMER_NO="999"),
        ])
        self.db.signing_submissions.insert_one({"token": "t", "customer_id": str(self.ids[0])})
        self.db.inventory.insert_one({"category": "panel", "company": "UTL", "spec": "540", "stock": 10})
        self.db.users.insert_one({"email": "admin@x"})
        self.storage = FakeStorage()
        self.storage.objects[f"customers/{self.ids[0]}/WCR.pdf"] = b"%PDF-1"
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_export_delete_import(self):
        backup = cd.export(self.db, self.tmp / "b", with_files=True, storage=self.storage)
        self.assertTrue((backup / "files" / f"customers/{self.ids[0]}/WCR.pdf").is_file())

        cd.delete(self.db, backup, confirm=False)
        for name in cd.COLLECTIONS:
            self.assertEqual(self.db[name].count_documents({}), 0)
        self.assertEqual(self.db.users.count_documents({}), 1)          # untouched
        self.assertGreater(self.db.catalog_items.count_documents({}), 0)  # untouched

        self.storage.objects.clear()
        dry = cd.import_(self.db, backup, dry_run=True)
        self.assertEqual(dry["imported"], 2)
        self.assertEqual(self.db.customers.count_documents({}), 0)

        rep = cd.import_(self.db, backup, with_files=True, with_inventory=True, storage=self.storage)
        self.assertEqual((rep["imported"], rep["signing_submissions"], rep["inventory"]), (2, 1, 1))
        c = self.db.customers.find_one({"_id": self.ids[0]})            # same id → R2 docs still match
        self.assertEqual((c["SYSTEM_COST"], c["INVERTER_CAPACITY"]), (150000, 3.3))
        self.assertIn(f"customers/{self.ids[0]}/WCR.pdf", self.storage.objects)

        # Importing again skips everything already there.
        again = cd.import_(self.db, backup)
        self.assertEqual(again["imported"], 0)
        self.assertEqual(len(again["skipped"]), 2)

    def test_delete_refuses_if_backup_is_stale(self):
        backup = cd.export(self.db, self.tmp / "b")
        self.db.customers.insert_one({"CONSUMER_NAME": "Added later"})
        with self.assertRaises(SystemExit):
            cd.delete(self.db, backup, confirm=False)
        self.assertEqual(self.db.customers.count_documents({}), 3)

    def test_imported_customers_work_in_the_installations_query(self):
        backup = cd.export(self.db, self.tmp / "b")
        cd.delete(self.db, backup, confirm=False)
        cd.import_(self.db, backup)
        from test_installations_overview import _AsyncDB
        from app.routers import installations
        database.db = _AsyncDB(self.db)
        res = run(installations.installations_overview(
            search="", status="", pending_step="", done_step="", payment="due", dealer="",
            sort="money_ahead", page=1, limit=20, fetch_all=False, _=None))
        self.assertEqual(res["total"], 2)
        self.assertAlmostEqual(res["data"][0]["paid_percent"], 100 * 50000 / 150000)


if __name__ == "__main__":
    unittest.main()
