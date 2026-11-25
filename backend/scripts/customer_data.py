"""
Back up, wipe and restore customer data.

Run from the backend/ directory with the venv active; it uses MONGODB_URI (and
the R2 settings, for --with-files) from backend/.env.

    # 1. Export everything to backups/customers-<date>/ (data.json + files/)
    python scripts/customer_data.py export --with-files

    # 2. Delete customers, signing records and inventory stock from MongoDB.
    #    Refuses unless the backup holds every customer currently in the DB.
    python scripts/customer_data.py delete --backup backups/customers-<date>

    # 3. Later, if needed: put them back (converted to the typed format).
    python scripts/customer_data.py import --backup backups/customers-<date> --dry-run
    python scripts/customer_data.py import --backup backups/customers-<date>

What is exported (data.json, MongoDB Extended JSON so ids and types survive):
  customers, signing_submissions, inventory. Users and the dealer/equipment
  catalog are not touched by any command here.

Files: generated documents, signatures and uploads live in Cloudflare R2 under
customers/<id>/. `export --with-files` downloads them into files/; `delete`
leaves R2 alone (re-imported customers keep their _id, so their documents are
still found); `import --with-files` uploads them back.

Import converts old free-text values ("1,50,000", "5 kW", "15-03-2026",
INVERTER_GURANTEE, ...) to the typed format. A value that can't be converted
is set to null and its original text is kept on the customer under
`import_issues`, and listed in the report — nothing is silently lost.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from bson import json_util  # noqa: E402
from bson.json_util import RELAXED_JSON_OPTIONS  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.models.customer import CustomerCreate, derived_fields  # noqa: E402
from app.models.installation import compute_installation_date, merge_steps  # noqa: E402
from app.services.catalog_rules import CHOICE_FIELDS, Catalog  # noqa: E402

COLLECTIONS = ("customers", "signing_submissions", "inventory")
FORMAT_VERSION = 1


# ── Old (free-text) → typed conversion ────────────────────────────────────────

RENAMED = {
    "INVERTER_GURANTEE": "INVERTER_GUARANTEE",
    "PANEL_GURANTEE": "PANEL_GUARANTEE",
}
# Calculated now, never stored, or replaced by a calculation on import.
DROPPED = {
    "payment_status", "paid_percent", "total_payment", "received_payment",
    "TOTAL_PANEL_CAPACITY", "INVERTER_GUARANTEE", "PANEL_GUARANTEE",
    "inverter_sr_set_date", "panel_sr_set_date",
    # Meter details are no longer collected (the Meter Testing Letter was retired).
    "METER_TESTING_DATE", "METER_RECEIPT_NO", "METER_RECIPT_NO",
    "GENERATION_METER_MAKE", "GENERATION_METER_NO",
}
NUMERIC_FIELDS = {
    "SYSTEM_COST": "money", "AGREEMENT_SYSTEM_COST": "money",
    "SOLAR_CAPACITY": "number", "SANCTIONED_CAPACITY": "number", "INVERTER_CAPACITY": "number",
    "PANEL_WATT": "number", "NO_OF_PANEL": "number",
}
DATE_FIELDS = ("CONSUMER_APP_DATE", "SUBSIDY_APP_DATE")
CUSTOMER_FIELDS = set(CustomerCreate.model_fields)


def to_number(value, money=False):
    """'1,50,000' / '₹150000' / '150000/-' → 150000 (money is rounded to whole
    rupees); '5 kW' → 5, '3.3kW' → 3.3, '540 W' → 540. Returns the input
    unchanged when it isn't a single number (the typed model then reports it)."""
    if value is None or isinstance(value, (int, float)):
        return round(value) if money and isinstance(value, float) else value
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    m = re.fullmatch(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:kw|kwp|w|wp|/-)?", text, re.I)
    if not m:
        return value
    n = float(m.group(1))
    if money:
        return round(n)
    return int(n) if n.is_integer() else n


def to_iso_date(value):
    """'2026-03-15', '15-03-2026', '15/03/2026', '15.03.2026' → '2026-03-15'."""
    if value is None or isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else (value.isoformat() if value else None)
    text = str(value).strip()
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return value


def convert_customer(raw: dict, catalog: Catalog) -> tuple[dict, dict]:
    """Return (typed customer document, {field: original value it couldn't take})."""
    doc = {RENAMED.get(k, k): v for k, v in raw.items()}
    issues: dict = {}

    # Old single received_payment → one undated entry.
    payments = doc.get("received_payments")
    if not payments and doc.get("received_payment"):
        payments = [{"amount": doc.get("received_payment"), "date": None}]
    doc["received_payments"] = []
    for i, p in enumerate(payments or []):
        amount = to_number((p or {}).get("amount"), money=True)
        when = to_iso_date((p or {}).get("date"))
        if not isinstance(amount, int) or amount < 0:
            issues[f"received_payments[{i}]"] = p
            continue
        if when is not None and not _is_iso_date(when):
            issues[f"received_payments[{i}].date"] = when
            when = None
        doc["received_payments"].append({"amount": amount, "date": when})

    for k in DROPPED:
        doc.pop(k, None)

    # Customer data fields: pre-convert, then validate one by one through the
    # same model the API uses, so a bad value only blanks that one field.
    for field in CUSTOMER_FIELDS:
        if field not in doc:
            continue
        value = doc[field]
        if field in NUMERIC_FIELDS:
            value = to_number(value, money=NUMERIC_FIELDS[field] == "money")
        elif field in DATE_FIELDS:
            value = to_iso_date(value)
        try:
            doc[field] = CustomerCreate.model_validate({field: value}).to_store(only_sent=True)[field]
        except ValidationError:
            issues[field] = raw.get(field, raw.get(_old_name(field)))
            doc[field] = None

    # Choices that aren't in today's catalog are kept (like a hidden option)
    # but reported, so an admin can add them back to the list if needed.
    for field, list_type in CHOICE_FIELDS.items():
        value = doc.get(field)
        if value is None:
            continue
        item = catalog.find(list_type, value)
        if item is None:
            issues.setdefault("not_in_catalog", {})[field] = value
        elif isinstance(value, str):
            doc[field] = item["value"]

    steps = merge_steps(doc.get("installation_steps"))
    for s in steps:
        if s.get("completed_date"):
            iso = to_iso_date(s["completed_date"])
            s["completed_date"] = iso if _is_iso_date(iso) else None
    doc["installation_steps"] = [
        {k: s[k] for k in ("key", "status", "completed_date", "performed_by")} for s in steps
    ]
    doc["INSTALLATION_DATE"] = compute_installation_date(steps)

    doc.update(derived_fields(doc, catalog.warranty_years))
    if issues:
        doc["import_issues"] = {k: v for k, v in issues.items() if k != "not_in_catalog"} or None
        if doc["import_issues"] is None:
            doc.pop("import_issues")
    return doc, issues


def _old_name(field):
    return next((old for old, new in RENAMED.items() if new == field), field)


def _is_iso_date(v):
    try:
        date.fromisoformat(str(v))
        return True
    except ValueError:
        return False


# ── Commands ──────────────────────────────────────────────────────────────────

def _db():
    os.chdir(BACKEND_DIR)  # so pydantic-settings finds backend/.env
    from pymongo import MongoClient
    from app.core.config import settings
    return MongoClient(settings.MONGODB_URI)["solar_docs"]


def export(db, out: Path, with_files: bool = False, storage=None) -> Path:
    # Read everything first, so a failed connection doesn't leave an empty folder.
    data = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "collections": {name: list(db[name].find({})) for name in COLLECTIONS},
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "data.json").write_text(json_util.dumps(data, json_options=RELAXED_JSON_OPTIONS, indent=1),
                                   encoding="utf-8")
    counts = {k: len(v) for k, v in data["collections"].items()}
    files = 0
    if with_files:
        for c in data["collections"]["customers"]:
            prefix = c.get("r2_prefix") or storage.customer_prefix(str(c["_id"]))
            for obj in storage.list_objects(prefix):
                dest = out / "files" / obj["key"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(storage.download_bytes(obj["key"]))
                files += 1
    # Read it back to prove the file is complete before anyone deletes.
    check = load_backup(out)
    assert {k: len(v) for k, v in check["collections"].items()} == counts
    print(f"Exported to {out}: " + ", ".join(f"{n} {k}" for k, n in counts.items())
          + (f", {files} files" if with_files else ""))
    return out


def load_backup(path: Path) -> dict:
    data = json_util.loads((Path(path) / "data.json").read_text(encoding="utf-8"))
    if data.get("format_version") != FORMAT_VERSION:
        raise SystemExit(f"Unknown backup format in {path}")
    return data


def delete(db, backup: Path, confirm: bool = True) -> dict:
    """Delete the exported collections, but only if `backup` holds every
    customer currently in the database."""
    saved = {str(c["_id"]) for c in load_backup(backup)["collections"]["customers"]}
    live = {str(c["_id"]) for c in db.customers.find({}, {"_id": 1})}
    missing = live - saved
    if missing:
        raise SystemExit(f"Not deleting: {len(missing)} customers in the database are not in this backup "
                         f"(added after the export?). Export again first.")
    counts = {name: db[name].count_documents({}) for name in COLLECTIONS}
    print("About to delete: " + ", ".join(f"{n} {k}" for k, n in counts.items()))
    if confirm and input("Type DELETE to continue: ").strip() != "DELETE":
        raise SystemExit("Cancelled — nothing deleted.")
    for name in COLLECTIONS:
        db[name].delete_many({})
    print("Deleted. Users, the dealer/equipment catalog and R2 files were not touched.")
    return counts


def import_(db, backup: Path, dry_run: bool = False, with_files: bool = False,
            with_inventory: bool = False, storage=None) -> dict:
    data = load_backup(backup)["collections"]
    catalog = Catalog(list(db.catalog_items.find({})))
    report = {"imported": 0, "skipped": [], "issues": {}}

    existing_ids = {c["_id"] for c in db.customers.find({}, {"_id": 1})}
    existing_nos = {c.get("CONSUMER_NO") for c in db.customers.find({}, {"CONSUMER_NO": 1})}
    to_insert = []
    for raw in data["customers"]:
        name = raw.get("CONSUMER_NAME") or str(raw["_id"])
        doc, issues = convert_customer(raw, catalog)
        if doc["_id"] in existing_ids:
            report["skipped"].append(f"{name}: already in the database (same id)")
            continue
        if doc.get("CONSUMER_NO") and doc["CONSUMER_NO"] in existing_nos:
            report["skipped"].append(f"{name}: consumer no {doc['CONSUMER_NO']} already in the database")
            continue
        existing_nos.add(doc.get("CONSUMER_NO"))
        if issues:
            report["issues"][name] = issues
        to_insert.append(doc)

    imported_ids = {d["_id"] for d in to_insert}
    subs = [s for s in data.get("signing_submissions", [])
            if _oid(s.get("customer_id")) in imported_ids
            and not db.signing_submissions.find_one({"_id": s["_id"]}, {"_id": 1})]
    inv = data.get("inventory", []) if with_inventory else []

    if not dry_run:
        if to_insert:
            db.customers.insert_many(to_insert)
        if subs:
            db.signing_submissions.insert_many(subs)
        for item in inv:
            db.inventory.replace_one({"category": item["category"], "company": item["company"],
                                      "spec": item["spec"]}, item, upsert=True)
        if with_files:
            root = Path(backup) / "files"
            for d in to_insert:
                prefix = d.get("r2_prefix") or storage.customer_prefix(str(d["_id"]))
                folder = root / prefix
                if folder.is_dir():
                    for f in folder.rglob("*"):
                        if f.is_file():
                            storage.upload_bytes(f.read_bytes(), f.relative_to(root).as_posix())

    report["imported"] = len(to_insert)
    report["signing_submissions"] = len(subs)
    report["inventory"] = len(inv)
    _print_report(report, dry_run)
    return report


def _oid(v):
    from bson import ObjectId
    try:
        return ObjectId(str(v))
    except Exception:
        return None


def _print_report(report, dry_run):
    verb = "Would import" if dry_run else "Imported"
    print(f"{verb} {report['imported']} customers, {report['signing_submissions']} signing records, "
          f"{report['inventory']} inventory lines.")
    for s in report["skipped"]:
        print(f"  skipped  {s}")
    for name, issues in report["issues"].items():
        for field, value in issues.items():
            if field == "not_in_catalog":
                for f, v in value.items():
                    print(f"  note     {name}: {f} “{v}” isn't in the dealer/equipment lists (kept)")
            else:
                print(f"  CHECK    {name}: {field} = {value!r} couldn't be converted — left blank, "
                      f"original kept in import_issues")
    if dry_run:
        print("Dry run — nothing was written.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write a backup folder")
    e.add_argument("--out", type=Path,
                   default=BACKEND_DIR / "backups" / f"customers-{datetime.now():%Y%m%d-%H%M%S}")
    e.add_argument("--with-files", action="store_true", help="also download R2 documents/uploads")
    d = sub.add_parser("delete", help="delete customer data that is in a backup")
    d.add_argument("--backup", type=Path, required=True)
    i = sub.add_parser("import", help="restore a backup (converted to the typed format)")
    i.add_argument("--backup", type=Path, required=True)
    i.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    i.add_argument("--with-files", action="store_true", help="upload the backup's files/ back to R2")
    i.add_argument("--with-inventory", action="store_true", help="also restore inventory stock lines")
    args = ap.parse_args()

    db = _db()
    storage = None
    if getattr(args, "with_files", False):
        from app.services import storage as storage  # noqa: F811
    if args.cmd == "export":
        export(db, args.out, args.with_files, storage)
    elif args.cmd == "delete":
        delete(db, args.backup)
    else:
        import_(db, args.backup, args.dry_run, args.with_files, args.with_inventory, storage)


if __name__ == "__main__":
    main()
