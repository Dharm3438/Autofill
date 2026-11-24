"""Derived payment status (paid / due / no_cost). Run from backend/:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.installation import compute_payment_status  # noqa: E402


class PaymentStatusTest(unittest.TestCase):
    def test_no_cost_when_system_cost_missing_or_unparseable(self):
        self.assertEqual(compute_payment_status({}), "no_cost")
        self.assertEqual(compute_payment_status({"SYSTEM_COST": ""}), "no_cost")
        self.assertEqual(compute_payment_status({"SYSTEM_COST": "TBD"}), "no_cost")
        # Received money without a cost still can't be judged "paid".
        self.assertEqual(
            compute_payment_status({"received_payments": [{"amount": 5000}]}), "no_cost"
        )

    def test_due_until_received_covers_cost(self):
        c = {"SYSTEM_COST": "₹1,50,000", "received_payments": [{"amount": 100000, "date": None}]}
        self.assertEqual(compute_payment_status(c), "due")
        c["received_payments"].append({"amount": 50000, "date": "2026-01-01"})
        self.assertEqual(compute_payment_status(c), "paid")

    def test_overpaid_counts_as_paid(self):
        c = {"SYSTEM_COST": "1000", "received_payments": [{"amount": 1200}]}
        self.assertEqual(compute_payment_status(c), "paid")

    def test_legacy_single_received_value(self):
        self.assertEqual(
            compute_payment_status({"SYSTEM_COST": "1000", "received_payment": "1000"}), "paid"
        )
        self.assertEqual(compute_payment_status({"SYSTEM_COST": "1000"}), "due")


if __name__ == "__main__":
    unittest.main()
