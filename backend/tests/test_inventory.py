"""Inventory tracks only solar panels and inverters."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError  # noqa: E402

from app.models.inventory import CATEGORIES, StockUpdate  # noqa: E402
from app.routers.inventory import _demand_lines  # noqa: E402


class InventoryCategoriesTest(unittest.TestCase):
    def test_only_panels_and_inverters(self):
        self.assertEqual(CATEGORIES, ("panel", "inverter"))

    def test_customer_demand_has_no_meter_lines(self):
        customer = {"NO_OF_PANEL": 6, "PANEL_COMPANY": "UTL", "PANEL_WATT": 540,
                    "INVERTER_MAKE": "UTL", "INVERTER_CAPACITY": 3.3}
        lines = _demand_lines(customer, {"panel": False, "inverter": True})
        self.assertEqual([(cat, qty, done) for cat, _, _, qty, done in lines],
                         [("panel", 6, False), ("inverter", 1, True)])
        # A customer with no equipment chosen yet adds no demand at all.
        self.assertEqual(_demand_lines({}, {"panel": False, "inverter": False}), [])

    def test_meter_stock_rejected(self):
        for category in ("generation_meter", "net_meter"):
            with self.assertRaises(ValidationError):
                StockUpdate(category=category, stock=5)


if __name__ == "__main__":
    unittest.main()
