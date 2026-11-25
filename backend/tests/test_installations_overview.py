"""
Installations overview pagination tests. Run from backend/:

    pip install mongomock
    venv\\Scripts\\python -m unittest discover -s tests -v

The overview filters, sorts and pages inside MongoDB (an aggregation
pipeline), so these tests run it against mongomock — an in-memory MongoDB
emulator — and check it agrees with the Python progress logic
(merge_steps / compute_overall_status). Skipped if mongomock isn't installed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

try:
    import mongomock
except ImportError:  # pragma: no cover
    mongomock = None

from app.core import database  # noqa: E402
from app.models.installation import INSTALLATION_STEPS  # noqa: E402
from app.routers import installations  # noqa: E402

from test_permissions import run  # noqa: E402

KEYS = [s["key"] for s in INSTALLATION_STEPS]


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, length=None):
        return self._docs if length is None else self._docs[:length]


class _AsyncCollection:
    """Just enough of motor's collection API for the overview endpoint."""

    def __init__(self, coll):
        self._coll = coll

    def aggregate(self, pipeline):
        return _AsyncCursor(self._coll.aggregate(pipeline))


class _AsyncDB:
    def __init__(self, db):
        self.customers = _AsyncCollection(db.customers)


def paid(percent, cost=1000):
    """Customer fields for a job `percent` paid (two dated instalments)."""
    received = cost * percent // 100
    return {"SYSTEM_COST": cost, "received_payments": [
        {"amount": received // 2, "date": "2026-01-01"},
        {"amount": received - received // 2, "date": "2026-02-01"},
    ]}


def _steps(done_keys):
    return [{"key": k, "status": "done" if k in done_keys else "pending"} for k in KEYS]


@unittest.skipIf(mongomock is None, "mongomock not installed")
class OverviewTest(unittest.TestCase):
    def setUp(self):
        self.raw = mongomock.MongoClient().db
        database.db = _AsyncDB(self.raw)

    def add(self, name, done=(), dealer="D1", **extra):
        self.raw.customers.insert_one(
            {"CONSUMER_NAME": name, "DEALER_NAME": dealer, "installation_steps": _steps(done), **extra}
        )

    def overview(self, **kw):
        params = dict(search="", status="", pending_step="", done_step="", payment="", dealer="", sort="progress", page=1, limit=20, fetch_all=False)
        params.update(kw)
        return run(installations.installations_overview(**params, _=None))

    def names(self, res):
        return [r["CONSUMER_NAME"] for r in res["data"]]

    def test_sorted_by_progress_then_name_case_insensitive(self):
        self.add("charlie", done=KEYS[:2])
        self.add("Bravo", done=KEYS[:2])
        self.add("alpha", done=KEYS[:1])
        self.add("Zed", done=KEYS)
        res = self.overview()
        self.assertEqual(self.names(res), ["Zed", "Bravo", "charlie", "alpha"])
        self.assertEqual(res["total"], 4)

    def test_pages_do_not_overlap_and_cover_everything(self):
        for i in range(45):
            self.add(f"C{i:02d}", done=KEYS[: i % 5])
        seen = []
        for page in (1, 2, 3):
            res = self.overview(page=page, limit=20)
            self.assertEqual(res["total"], 45)
            seen += [r["id"] for r in res["data"]]
        self.assertEqual(len(seen), 45)
        self.assertEqual(len(set(seen)), 45)
        self.assertEqual(self.overview(page=3, limit=20)["data"].__len__(), 5)
        self.assertEqual(self.overview(page=4, limit=20)["data"], [])

    def test_fetch_all_ignores_paging(self):
        for i in range(25):
            self.add(f"C{i:02d}")
        res = self.overview(fetch_all=True, page=2, limit=5)
        self.assertEqual(len(res["data"]), 25)

    def test_status_matches_python_logic(self):
        self.add("none")
        self.add("legacy", installation_steps=None)  # created before the feature
        self.add("garbled", installation_steps="oops")
        self.add("some", done=KEYS[:3])
        self.add("all", done=KEYS)
        # Unknown and duplicate done keys must not inflate the count.
        self.raw.customers.insert_one({
            "CONSUMER_NAME": "junk",
            "installation_steps": [
                {"key": KEYS[0], "status": "done"},
                {"key": KEYS[0], "status": "done"},
                {"key": "removed_step", "status": "done"},
            ],
        })
        res = self.overview(fetch_all=True)
        by_name = {r["CONSUMER_NAME"]: r for r in res["data"]}
        self.assertEqual(by_name["none"]["overall_status"], "not_started")
        self.assertEqual(by_name["legacy"]["overall_status"], "not_started")
        self.assertEqual(by_name["garbled"]["overall_status"], "not_started")
        self.assertEqual(by_name["some"]["overall_status"], "in_progress")
        self.assertEqual(by_name["all"]["overall_status"], "completed")
        self.assertEqual(by_name["junk"]["done_count"], 1)
        # The DB-side status filter agrees with the Python-computed status.
        for st in ("not_started", "in_progress", "completed"):
            got = sorted(self.names(self.overview(status=st, fetch_all=True)))
            want = sorted(n for n, r in by_name.items() if r["overall_status"] == st)
            self.assertEqual(got, want, st)

    def test_pending_step_filter(self):
        self.add("has_first", done=KEYS[:1])
        self.add("missing_first", done=KEYS[1:2])
        self.add("legacy", installation_steps=None)
        res = self.overview(pending_step=KEYS[0])
        self.assertEqual(sorted(self.names(res)), ["legacy", "missing_first"])
        self.assertEqual(res["total"], 2)
        self.assertEqual(self.overview(pending_step="not_a_step")["data"], [])

    def test_summary_counts_all_customers_before_row_filters(self):
        self.add("a", done=KEYS)
        self.add("b", done=KEYS[:1])
        self.add("c")
        self.add("other dealer", dealer="D2")
        res = self.overview(dealer="D1", status="completed", page=1, limit=1)
        s = res["summary"]
        self.assertEqual(s["total_customers"], 3)
        self.assertEqual((s["completed"], s["in_progress"], s["not_started"]), (1, 1, 1))
        self.assertEqual(s["per_step_pending"][KEYS[0]], 1)
        self.assertEqual(s["per_step_pending"][KEYS[-1]], 2)
        self.assertEqual(self.names(res), ["a"])
        self.assertEqual(res["total"], 1)

    def test_rows_keep_payment_fields(self):
        self.add("payer", SYSTEM_COST=100000, received_payments=[{"amount": 20000, "date": "2026-01-01"}])
        row = self.overview()["data"][0]
        self.assertEqual((row["total_payment"], row["received_payment"], row["remaining_payment"]),
                         (100000, 20000, 80000))
        self.assertEqual(len(row["steps"]), len(KEYS))
        self.assertEqual(row["payment_status"], "due")
        self.assertEqual(row["paid_percent"], 20)

    def test_done_step_filter(self):
        self.add("has_first", done=KEYS[:1])
        self.add("none")
        self.add("no_steps", installation_steps=None)
        self.assertEqual(self.names(self.overview(done_step=KEYS[0])), ["has_first"])
        self.assertEqual(self.overview(done_step="not_a_step")["data"], [])

    def test_done_and_pending_step_combine(self):
        self.add("both", done=KEYS[:2])
        self.add("first_only", done=KEYS[:1])
        res = self.overview(done_step=KEYS[0], pending_step=KEYS[1])
        self.assertEqual(self.names(res), ["first_only"])

    def test_payment_filter_is_calculated_from_amounts(self):
        self.add("paid", **paid(100))
        self.add("overpaid", **paid(120))
        self.add("due", **paid(40))
        self.add("nothing_yet", **paid(0))
        self.add("no_cost", SYSTEM_COST=None)
        self.assertEqual(self.names(self.overview(payment="due")), ["due", "nothing_yet"])
        self.assertEqual(self.names(self.overview(payment="paid")), ["overpaid", "paid"])
        self.assertEqual(self.names(self.overview(payment="no_cost")), ["no_cost"])
        self.assertEqual(self.overview(payment="bogus")["data"], [])
        # Summary ignores the payment filter, like the other row filters.
        self.assertEqual(self.overview(payment="due")["summary"]["total_customers"], 5)

    def test_database_and_python_payment_maths_agree(self):
        cases = [paid(0), paid(33), paid(100), paid(150), {"SYSTEM_COST": None},
                 {"SYSTEM_COST": 999, "received_payments": []}]
        for i, extra in enumerate(cases):
            self.add(f"c{i}", **extra)
        for row in self.overview(fetch_all=True)["data"]:
            raw = self.raw.customers.find_one({"CONSUMER_NAME": row["CONSUMER_NAME"]})
            # The row's values come from payment_info; the pipeline computed its
            # own for filtering/sorting. Both must match.
            doc = list(self.raw.customers.aggregate(
                installations._overview_base_pipeline({"_id": raw["_id"]})))[0]
            self.assertAlmostEqual(doc["paid_percent"], row["paid_percent"], places=6)
            self.assertEqual(doc["payment_status"], row["payment_status"])

    def test_subsidy_received_but_balance_due(self):
        subsidy = "subsidy_received"
        self.add("owes", done=[subsidy], **paid(50))
        self.add("settled", done=[subsidy], **paid(100))
        self.add("waiting", **paid(50))
        res = self.overview(done_step=subsidy, payment="due")
        self.assertEqual(self.names(res), ["owes"])

    def test_money_ahead_sort(self):
        half = len(KEYS) // 2
        # 50% paid, nothing started → +50: the one to start first.
        self.add("paid_not_started", **paid(50))
        # 80% paid, half the work done → +30.
        self.add("paid_half_done", done=KEYS[:half], **paid(80))
        # Fully paid and fully done → 0, as is nothing paid and nothing done;
        # the tie goes to the higher paid %.
        self.add("all_done", done=KEYS, **paid(100))
        self.add("fresh", **paid(0))
        # No cost set → treated as 0% paid.
        self.add("no_cost", SYSTEM_COST=None)
        # Work well ahead of payment → negative, last.
        self.add("work_ahead", done=KEYS[:-1], **paid(20))
        res = self.overview(sort="money_ahead")
        self.assertEqual(self.names(res),
                         ["paid_not_started", "paid_half_done", "all_done", "fresh", "no_cost", "work_ahead"])
        # The default sort is unchanged: most steps done first.
        self.assertEqual(self.names(self.overview())[:2], ["all_done", "work_ahead"])

    def test_money_ahead_sort_pages_and_filters(self):
        for i in range(5):
            self.add(f"c{i}", **paid(i * 20))
        first = self.names(self.overview(sort="money_ahead", limit=2))
        second = self.names(self.overview(sort="money_ahead", limit=2, page=2))
        self.assertEqual(first + second, ["c4", "c3", "c2", "c1"])
        res = self.overview(sort="money_ahead", status="not_started", fetch_all=True)
        self.assertEqual(self.names(res), ["c4", "c3", "c2", "c1", "c0"])

    def test_unknown_sort_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.overview(sort="bogus")
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
