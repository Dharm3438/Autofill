"""Step-group tests (shared date / done-by). Run from backend/:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

from app.models.installation import (  # noqa: E402
    INSTALLATION_STEPS,
    InstallationGroupUpdate,
    apply_group_update,
    group_step_keys,
    merge_steps,
)

WIRING = ["wiring", "earthing_la", "acdb", "dcdb", "generation_meter"]


class GroupTest(unittest.TestCase):
    def test_wiring_group_members_are_adjacent(self):
        keys = [s["key"] for s in INSTALLATION_STEPS]
        self.assertEqual(group_step_keys("wiring"), WIRING)
        start = keys.index(WIRING[0])
        self.assertEqual(keys[start:start + len(WIRING)], WIRING)

    def test_done_members_share_date_and_person(self):
        steps = merge_steps(None)
        apply_group_update(steps, "wiring", InstallationGroupUpdate(
            done_keys=["wiring", "acdb", "inverter"],  # inverter isn't a member: ignored
            completed_date="2026-11-20", performed_by="Pranav",
        ))
        by = {s["key"]: s for s in steps}
        for k in ("wiring", "acdb"):
            self.assertEqual((by[k]["status"], by[k]["completed_date"], by[k]["performed_by"]),
                             ("done", "2026-11-20", "Pranav"))
        for k in ("earthing_la", "dcdb", "generation_meter", "inverter"):
            self.assertEqual(by[k]["status"], "pending")

    def test_unticked_member_is_cleared(self):
        stored = [{"key": "dcdb", "status": "done", "completed_date": "2026-01-01", "performed_by": "X"}]
        steps = merge_steps(stored)
        apply_group_update(steps, "wiring", InstallationGroupUpdate(done_keys=["wiring"]))
        by = {s["key"]: s for s in steps}
        self.assertEqual((by["dcdb"]["status"], by["dcdb"]["completed_date"], by["dcdb"]["performed_by"]),
                         ("pending", None, None))
        self.assertEqual(by["wiring"]["status"], "done")
        self.assertTrue(by["wiring"]["completed_date"])  # defaults to today

    def test_merge_steps_drops_legacy_notes(self):
        steps = merge_steps([{"key": "structure", "status": "done", "notes": "old"}])
        self.assertNotIn("notes", steps[0])


class LocalDateTest(unittest.TestCase):
    """Defaults use India's calendar day, not the server's UTC day."""

    def test_just_after_midnight_in_india_is_already_the_new_day(self):
        from datetime import date, datetime, timezone
        from unittest import mock
        from app.core import localtime

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                # 19:00 UTC on 4 March = 00:30 IST on 5 March
                return datetime(2026, 3, 4, 19, 0, tzinfo=timezone.utc).astimezone(tz)

        with mock.patch.object(localtime, "datetime", Frozen):
            self.assertEqual(localtime.local_today(), date(2026, 3, 5))


class StepDoneByTest(unittest.TestCase):
    """PUT /installations/{id}/steps/{key}: the "Done by" name can be cleared."""

    def setUp(self):
        import asyncio
        from bson import ObjectId
        from app.core import database
        from test_auth import FakeDB, FakeCollection
        self.asyncio = asyncio
        self.db = FakeDB()
        self.db.customers = FakeCollection()
        database.db = self.db
        self.cid = ObjectId()
        self.db.customers.docs.append({"_id": self.cid, "installation_steps": [
            {"key": "structure", "status": "done", "completed_date": "2026-03-01", "performed_by": "Ravi"},
        ]})

    def save(self, **body):
        from app.models.installation import InstallationStepUpdate
        from app.routers.installations import update_installation_step
        self.asyncio.run(update_installation_step(str(self.cid), "structure", InstallationStepUpdate(**body)))
        steps = self.db.customers.docs[0]["installation_steps"]
        return next(s for s in steps if s["key"] == "structure")

    def test_blank_done_by_clears_it(self):
        step = self.save(status="done", completed_date="2026-03-01", performed_by=None)
        self.assertIsNone(step.get("performed_by"))

    def test_done_by_not_sent_is_kept(self):
        step = self.save(status="done", completed_date="2026-03-02")
        self.assertEqual(step["performed_by"], "Ravi")

    def test_new_name_replaces_old(self):
        step = self.save(status="done", completed_date="2026-03-01", performed_by="Asha")
        self.assertEqual(step["performed_by"], "Asha")


if __name__ == "__main__":
    unittest.main()
