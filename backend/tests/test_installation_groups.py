"""Step-group tests (shared date / done-by). Run from backend/:

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


if __name__ == "__main__":
    unittest.main()
