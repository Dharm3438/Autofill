"""
Agreement system cost tests. Run from backend/:

    venv\\Scripts\\python -m unittest discover -s tests -v

SYSTEM_COST is the real price (payments, customer details sheet). Documents
must print AGREEMENT_SYSTEM_COST instead, and only document users may see or
set it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

from app.core import database  # noqa: E402
from app.models.customer import CustomerUpdate  # noqa: E402
from app.routers import customers  # noqa: E402
from app.services.doc_generation import (  # noqa: E402
    required_fields_by_document,
    validate_customer_for_generation,
)

from test_permissions import FakeDB, make_user, run, _body  # noqa: E402


class TemplateTest(unittest.TestCase):
    def test_no_template_prints_the_real_system_cost(self):
        for doc_type, fields in required_fields_by_document().items():
            self.assertNotIn("SYSTEM_COST", fields, f"{doc_type} uses ${{SYSTEM_COST}}$")

    def test_np_agreement_uses_agreement_cost(self):
        self.assertIn("AGREEMENT_SYSTEM_COST", required_fields_by_document()["NP_Agreement"])

    def test_generation_blocked_until_agreement_cost_set(self):
        fields = set().union(*required_fields_by_document().values())
        customer = {k: "x" for k in fields}
        customer["SYSTEM_COST"] = 150000
        customer.pop("AGREEMENT_SYSTEM_COST")
        report = validate_customer_for_generation(customer)
        self.assertIsNotNone(report)
        keys = [f["key"] for f in report["missing_fields"]]
        self.assertEqual(keys, ["AGREEMENT_SYSTEM_COST"])


class AccessTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        database.db = self.db
        self.alice = make_user("data_entry")
        self.docs = make_user("documents")
        self.a1 = run(customers.create_customer(_body("Alice One", "A1"), user=self.alice))["data"]

    def _stored(self):
        return next(d for d in self.db.customers.docs if str(d["_id"]) == self.a1["id"])

    def test_data_entry_cannot_set_on_create(self):
        # _body fills every field, including AGREEMENT_SYSTEM_COST.
        self.assertIsNone(self._stored().get("AGREEMENT_SYSTEM_COST"))

    def test_documents_user_can_set_and_see(self):
        res = run(customers.update_customer(
            self.a1["id"], CustomerUpdate(AGREEMENT_SYSTEM_COST=120000), user=self.docs))
        self.assertEqual(res["data"]["AGREEMENT_SYSTEM_COST"], 120000)
        self.assertEqual(self._stored()["SYSTEM_COST"], 1)  # real cost untouched

    def test_data_entry_cannot_set_blank_or_see(self):
        run(customers.update_customer(
            self.a1["id"], CustomerUpdate(AGREEMENT_SYSTEM_COST=120000), user=self.docs))
        res = run(customers.update_customer(
            self.a1["id"], CustomerUpdate(AGREEMENT_SYSTEM_COST=""), user=self.alice))
        self.assertNotIn("AGREEMENT_SYSTEM_COST", res["data"])
        self.assertEqual(self._stored()["AGREEMENT_SYSTEM_COST"], 120000)


if __name__ == "__main__":
    unittest.main()
