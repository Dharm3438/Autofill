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
        params = dict(search="", status="", pending_step="", done_step="", payment="", dealer="", page=1, limit=20, fetch_all=False)
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
        self.add("payer", SYSTEM_COST="100000", received_payments=[{"amount": 20000, "date": "2026-01-01"}])
        row = self.overview()["data"][0]
        self.assertEqual((row["total_payment"], row["received_payment"], row["remaining_payment"]),
                         (100000, 20000, 80000))
        self.assertEqual(len(row["steps"]), len(KEYS))
        self.assertEqual(row["payment_status"], "due")

    def test_done_step_filter(self):
        self.add("has_first", done=KEYS[:1])
        self.add("none")
        self.add("legacy", installation_steps=None)
        self.assertEqual(self.names(self.overview(done_step=KEYS[0])), ["has_first"])
        self.assertEqual(self.overview(done_step="not_a_step")["data"], [])

    def test_done_and_pending_step_combine(self):
        self.add("both", done=KEYS[:2])
        self.add("first_only", done=KEYS[:1])
        res = self.overview(done_step=KEYS[0], pending_step=KEYS[1])
        self.assertEqual(self.names(res), ["first_only"])

    def test_payment_filter(self):
        self.add("paid", payment_status="paid")
        self.add("due", payment_status="due")
        self.add("no_cost", payment_status="no_cost")
        self.assertEqual(self.names(self.overview(payment="due")), ["due"])
        self.assertEqual(self.names(self.overview(payment="paid")), ["paid"])
        self.assertEqual(self.overview(payment="bogus")["data"], [])
        # Summary ignores the payment filter, like the other row filters.
        self.assertEqual(self.overview(payment="due")["summary"]["total_customers"], 3)

    def test_subsidy_received_but_balance_due(self):
        subsidy = "subsidy_received"
        self.add("owes", done=[subsidy], payment_status="due")
        self.add("settled", done=[subsidy], payment_status="paid")
        self.add("waiting", payment_status="due")
        res = self.overview(done_step=subsidy, payment="due")
        self.assertEqual(self.names(res), ["owes"])


if __name__ == "__main__":
    unittest.main()
