"""Dealer & equipment option lists (catalog). Run from backend/:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bson import ObjectId  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.core import database  # noqa: E402
from app.core.permissions import P, require  # noqa: E402
from app.models.catalog import (  # noqa: E402
    DEFAULTS, CatalogItemCreate, CatalogItemUpdate, normalize_value, normalize_warranty,
)
from app.routers import catalog  # noqa: E402
from test_permissions import FakeCollection, FakeDB, make_user, run  # noqa: E402


class CatalogDB(FakeDB):
    def __init__(self):
        super().__init__()
        self.catalog_items = FakeCollection()


def _items(res, type_):
    return res["data"]["items"][type_]


class NormalizeTest(unittest.TestCase):
    def test_capacity_formats_collapse_to_one(self):
        for raw in ("7", "7kw", "7 KW", " 7.0 kW ", "7.00"):
            self.assertEqual(normalize_value("inverter_capacity", raw), "7 kW")
        self.assertEqual(normalize_value("inverter_capacity", "3.30"), "3.3 kW")

    def test_watt_is_a_plain_number(self):
        for raw in ("550", "550W", "550 wp"):
            self.assertEqual(normalize_value("panel_watt", raw), "550")

    def test_bad_numbers_rejected(self):
        for type_, raw in (("inverter_capacity", "seven"), ("inverter_capacity", "7 W"),
                           ("panel_watt", "550 kW"), ("panel_watt", "0"), ("dealer", "   ")):
            with self.assertRaises(ValueError):
                normalize_value(type_, raw)

    def test_text_whitespace_collapsed(self):
        self.assertEqual(normalize_value("dealer", "  Ramesh   Patil "), "Ramesh Patil")

    def test_warranty(self):
        for raw in ("10", "10 years", "10 YEAR", "10yr"):
            self.assertEqual(normalize_warranty(raw), "10 YEAR")
        for raw in ("", "ten", "0"):
            with self.assertRaises(ValueError):
                normalize_warranty(raw)

    def test_defaults_are_already_canonical(self):
        # The seed must not rewrite values existing customers already carry.
        for type_, entries in DEFAULTS.items():
            for e in entries:
                value = e if isinstance(e, str) else e[0]
                self.assertEqual(normalize_value(type_, value), value)


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.db = CatalogDB()
        database.db = self.db

    def test_seeds_defaults_and_meter_makes_from_customers(self):
        self.db.customers.docs.extend([
            {"_id": ObjectId(), "GENERATION_METER_MAKE": "Secure"},
            {"_id": ObjectId(), "GENERATION_METER_MAKE": " secure "},
            {"_id": ObjectId(), "GENERATION_METER_MAKE": "HPL"},
            {"_id": ObjectId(), "GENERATION_METER_MAKE": ""},
            {"_id": ObjectId()},
        ])
        run(database.seed_catalog(self.db))
        res = run(catalog.list_catalog(_=None))
        self.assertEqual(len(_items(res, "dealer")), len(DEFAULTS["dealer"]))
        polycab = next(i for i in _items(res, "inverter_make") if i["value"] == "Polycab")
        self.assertEqual(polycab["warranty"], "8 YEAR")
        self.assertEqual([i["value"] for i in _items(res, "generation_meter_make")], ["HPL", "Secure"])
        # Numeric lists sort by number, not text.
        watts = [i["value"] for i in _items(res, "panel_watt")]
        self.assertEqual(watts, sorted(watts, key=float))

    def test_seed_is_idempotent_and_respects_admin_changes(self):
        run(database.seed_catalog(self.db))
        n = len(self.db.catalog_items.docs)
        office = next(d for d in self.db.catalog_items.docs if d["value"] == "Office")
        office["active"] = False
        run(database.seed_catalog(self.db))
        self.assertEqual(len(self.db.catalog_items.docs), n)
        self.assertFalse(next(d for d in self.db.catalog_items.docs if d["value"] == "Office")["active"])


class CatalogRouterTest(unittest.TestCase):
    def setUp(self):
        self.db = CatalogDB()
        database.db = self.db
        run(database.seed_catalog(self.db))
        self.admin = make_user("admin")

    def _add(self, type_, value, warranty=None):
        return run(catalog.add_catalog_item(
            CatalogItemCreate(type=type_, value=value, warranty=warranty), user=self.admin))["data"]

    def test_admin_adds_capacity_in_canonical_form(self):
        item = self._add("inverter_capacity", "7kw")
        self.assertEqual(item["value"], "7 kW")
        values = [i["value"] for i in _items(run(catalog.list_catalog(_=None)), "inverter_capacity")]
        self.assertEqual(values.index("7 kW"), values.index("6 kW") + 1)

    def test_make_needs_a_warranty(self):
        with self.assertRaises(HTTPException) as ctx:
            self._add("inverter_make", "Luminous")
        self.assertEqual(ctx.exception.status_code, 400)
        item = self._add("inverter_make", "Luminous", "12 years")
        self.assertEqual(item["warranty"], "12 YEAR")

    def test_dealer_ignores_warranty(self):
        item = self._add("dealer", "New Dealer", "5")
        self.assertNotIn("warranty", item)
        stored = next(d for d in self.db.catalog_items.docs if d["value"] == "New Dealer")
        self.assertNotIn("warranty", stored)
        self.assertEqual(stored["created_by"], str(self.admin["_id"]))

    def test_duplicates_rejected_case_insensitively(self):
        for value in ("polycab", "POLYCAB "):
            with self.assertRaises(HTTPException) as ctx:
                self._add("inverter_make", value, "8")
            self.assertEqual(ctx.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            self._add("inverter_capacity", "6")  # "6 kW" already seeded

    def test_same_value_allowed_in_different_lists(self):
        self._add("generation_meter_make", "UTL")  # UTL is also an inverter make

    def test_hidden_duplicate_points_to_reactivation(self):
        office = next(d for d in self.db.catalog_items.docs if d["value"] == "Office")
        run(catalog.update_catalog_item(str(office["_id"]), CatalogItemUpdate(active=False), _=None))
        with self.assertRaises(HTTPException) as ctx:
            self._add("dealer", "office")
        self.assertIn("hidden", ctx.exception.detail)

    def test_deactivate_keeps_item_listed_but_flagged(self):
        office = next(d for d in self.db.catalog_items.docs if d["value"] == "Office")
        run(catalog.update_catalog_item(str(office["_id"]), CatalogItemUpdate(active=False), _=None))
        row = next(i for i in _items(run(catalog.list_catalog(_=None)), "dealer") if i["value"] == "Office")
        self.assertFalse(row["active"])

    def test_update_warranty(self):
        utl = next(d for d in self.db.catalog_items.docs
                   if d["type"] == "panel_company" and d["value"] == "UTL")
        res = run(catalog.update_catalog_item(str(utl["_id"]), CatalogItemUpdate(warranty="25"), _=None))
        self.assertEqual(res["data"]["warranty"], "25 YEAR")

    def test_warranty_on_list_without_one_rejected(self):
        dealer = next(d for d in self.db.catalog_items.docs if d["type"] == "dealer")
        with self.assertRaises(HTTPException) as ctx:
            run(catalog.update_catalog_item(str(dealer["_id"]), CatalogItemUpdate(warranty="5"), _=None))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_id_404(self):
        for bad in ("nope", str(ObjectId())):
            with self.assertRaises(HTTPException) as ctx:
                run(catalog.update_catalog_item(bad, CatalogItemUpdate(active=False), _=None))
            self.assertEqual(ctx.exception.status_code, 404)


class CatalogAccessTest(unittest.TestCase):
    """Who can read the lists vs. change them."""

    def test_only_admin_manages(self):
        dep = require(P.CATALOG_MANAGE)
        run(dep(user=make_user("admin")))
        for role in ("data_entry", "installation", "documents"):
            with self.assertRaises(HTTPException) as ctx:
                run(dep(user=make_user(role)))
            self.assertEqual(ctx.exception.status_code, 403)

    def test_every_working_role_can_read(self):
        dep = require(*catalog._READERS, any_of=True)
        for role in ("admin", "data_entry", "installation", "documents"):
            run(dep(user=make_user(role)))
        with self.assertRaises(HTTPException):
            run(dep(user=make_user()))  # pending user


if __name__ == "__main__":
    unittest.main()
