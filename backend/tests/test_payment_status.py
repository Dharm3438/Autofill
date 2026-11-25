"""Payment maths (paid / due / no_cost, paid %). Run from backend/:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError  # noqa: E402

from app.models.installation import ReceivedPayment, payment_info  # noqa: E402


def info(cost, *amounts):
    return payment_info({"SYSTEM_COST": cost, "received_payments": [{"amount": a} for a in amounts]})


class PaymentInfoTest(unittest.TestCase):
    def test_no_cost(self):
        self.assertEqual(info(None)["payment_status"], "no_cost")
        self.assertEqual(info(0, 5000)["payment_status"], "no_cost")
        self.assertEqual(info(None, 5000)["paid_percent"], 0)

    def test_due_until_received_covers_cost(self):
        self.assertEqual(info(150000, 100000)["payment_status"], "due")
        self.assertEqual(info(150000, 100000, 50000)["payment_status"], "paid")
        self.assertEqual(info(150000, 100000)["remaining_payment"], 50000)

    def test_paid_percent_capped(self):
        self.assertEqual(info(100000, 50000)["paid_percent"], 50)
        self.assertEqual(info(1000, 1500)["paid_percent"], 100)
        self.assertEqual(info(1000, 1500)["remaining_payment"], 0)


class ReceivedPaymentTest(unittest.TestCase):
    def test_whole_rupees_and_real_dates(self):
        p = ReceivedPayment(amount="50000", date="2026-03-15")
        self.assertEqual((p.amount, p.date), (50000, "2026-03-15"))
        self.assertIsNone(ReceivedPayment(amount=1, date="").date)
        for bad in ({"amount": 10.5}, {"amount": -1}, {"amount": 1, "date": "15-03-2026"}):
            with self.assertRaises(ValidationError):
                ReceivedPayment(**bad)


if __name__ == "__main__":
    unittest.main()
