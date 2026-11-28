"""
Direct-from-R2 downloads (Render bills every byte the API sends out; R2
downloads are free). Run from backend/:

    python -m unittest discover -s tests -v

The server hands out short-lived links instead of file bytes. These tests
check the links describe exactly the bundle the server-built zip delivers,
and that the signing page gets the NP Agreement as two parts to join.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

import fitz  # noqa: E402  (PyMuPDF)
from bson import ObjectId  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.routers import documents, signing, uploads  # noqa: E402
from app.services import doc_generation as dg, storage  # noqa: E402

from test_permissions import FakeCollection, FakeDB, run  # noqa: E402

PREFIX = "customers/abc/"
NAME = "Ramesh_Patel"


def _obj(name, sub=""):
    return {"key": PREFIX + sub + name, "name": name, "size": 100}


FULL_FOLDER = [
    _obj(f"{NAME}_Annexure_1.pdf"),
    _obj(f"{NAME}_WCR_Aadhar.pdf"),
    _obj(f"{NAME}_NP_Agreement.pdf"),
    _obj(f"{NAME}_NP_Agreement_First_Page.pdf"),   # print copy, never delivered
    _obj("signature.png"),                           # internal
    _obj("installation.pdf", dg.UPLOAD_PREFIX),
    _obj("dcr.pdf", dg.UPLOAD_PREFIX),
    _obj("np_first_page_stamped.pdf", dg.UPLOAD_PREFIX),
]


def _pdf(pages: int, label: str) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"{label} {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def fake_link(key, expires_seconds=3600, *, filename=None, content_type=None):
    return f"https://r2.example/{key}?exp={expires_seconds}"


class FakeStorage:
    """Patches the storage functions the code under test calls."""

    def __init__(self, objects, blobs=None):
        self.objects = objects
        self.blobs = blobs or {}

    def __enter__(self):
        self._patches = [
            mock.patch.object(storage, "list_objects", lambda prefix: [o for o in self.objects if o["key"].startswith(prefix)]),
            mock.patch.object(storage, "presigned_url", side_effect=fake_link),
            mock.patch.object(storage, "object_exists", lambda key: any(o["key"] == key for o in self.objects)),
            mock.patch.object(storage, "download_bytes", lambda key: self.blobs[key]),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class BundleLinksTests(unittest.TestCase):
    def test_links_match_the_server_zip_and_flag_the_stamped_agreement(self):
        blobs = {o["key"]: _pdf(1, o["name"]) for o in FULL_FOLDER}
        blobs[PREFIX + dg.NP_STAMP_UPLOAD_KEY] = _pdf(1, "stamp")
        blobs[PREFIX + f"{NAME}_NP_Agreement.pdf"] = _pdf(3, "agreement")
        with FakeStorage(FULL_FOLDER, blobs):
            links = run(dg.bundle_links(PREFIX))
            bundle = run(dg.build_customer_bundle(PREFIX))

        self.assertEqual([f["name"] for f in links], [name for name, _ in bundle])
        self.assertEqual([f["name"] for f in links], [
            f"{NAME}_Annexure_1.pdf", f"{NAME}_NP_Agreement.pdf", f"{NAME}_WCR_Aadhar.pdf",
            dg.INSTALLATION_OUT_NAME, dg.DCR_OUT_NAME,
        ])
        stamped = [f for f in links if "stamp_url" in f]
        self.assertEqual([f["name"] for f in stamped], [f"{NAME}_NP_Agreement.pdf"])
        self.assertEqual(stamped[0]["stamp_url"], fake_link(PREFIX + dg.NP_STAMP_UPLOAD_KEY, dg.DOWNLOAD_LINK_SECONDS))
        # The server zip's agreement = stamp page + 3 agreement pages.
        agreement = dict(bundle)[f"{NAME}_NP_Agreement.pdf"]
        self.assertEqual(fitz.open(stream=agreement, filetype="pdf").page_count, 4)

    def test_no_stamp_means_no_merge(self):
        folder = [o for o in FULL_FOLDER if not o["key"].endswith(dg.NP_STAMP_UPLOAD_KEY)]
        with FakeStorage(folder):
            links = run(dg.bundle_links(PREFIX))
        self.assertFalse(any("stamp_url" in f for f in links))


class DocumentLinkEndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.cid = ObjectId()
        run(self.db.customers.insert_one({"_id": self.cid, "r2_prefix": PREFIX}))

    def test_bundle_links_endpoint(self):
        with FakeStorage(FULL_FOLDER), mock.patch.object(documents, "get_db", lambda: self.db):
            res = run(documents.download_links(str(self.cid), None))
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]["files"]), 5)

    def test_np_first_page_link_opens_inline_as_pdf(self):
        with FakeStorage(FULL_FOLDER), mock.patch.object(documents, "get_db", lambda: self.db):
            res = run(documents.np_first_page_link(str(self.cid), None))
            storage.presigned_url.assert_called_once_with(
                PREFIX + f"{NAME}_NP_Agreement_First_Page.pdf", dg.DOWNLOAD_LINK_SECONDS,
                filename=f"{NAME}_NP_Agreement_First_Page.pdf", content_type="application/pdf")
        self.assertTrue(res["data"]["url"].startswith("https://r2.example/"))

    def test_customer_without_documents_is_404(self):
        cid = ObjectId()
        run(self.db.customers.insert_one({"_id": cid}))
        with FakeStorage(FULL_FOLDER), mock.patch.object(documents, "get_db", lambda: self.db):
            with self.assertRaises(HTTPException) as e:
                run(documents.download_links(str(cid), None))
        self.assertEqual(e.exception.status_code, 404)

    def test_upload_preview_link(self):
        cid = "abc"  # customer_prefix("abc") == PREFIX
        with FakeStorage(FULL_FOLDER):
            res = run(uploads.preview_upload_link(cid, "dcr", None))
            with self.assertRaises(HTTPException) as unknown:
                run(uploads.preview_upload_link(cid, "passport", None))
        self.assertIn("uploads/dcr.pdf", res["data"]["url"])
        self.assertEqual(unknown.exception.status_code, 404)

    def test_presigned_url_asks_r2_for_inline_pdf_headers(self):
        client = mock.Mock()
        with mock.patch.object(storage, "_client", lambda: client):
            storage.presigned_url("k", 60, filename='Agreement — "final".pdf', content_type="application/pdf")
        params = client.generate_presigned_url.call_args.kwargs["Params"]
        self.assertEqual(params["ResponseContentType"], "application/pdf")
        self.assertEqual(params["ResponseContentDisposition"], 'inline; filename="Agreement  final.pdf"')


class SigningLinksTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.db.signing_submissions = FakeCollection()
        self.cid = ObjectId()
        manifest = [
            {"key": "0", "label": "Annexure-1", "r2_key": PREFIX + f"{NAME}_Annexure_1.pdf", "merge_stamp": False},
            {"key": "1", "label": "Net-Metering Agreement", "r2_key": PREFIX + f"{NAME}_NP_Agreement.pdf", "merge_stamp": True},
        ]
        run(self.db.customers.insert_one({"_id": self.cid, "r2_prefix": PREFIX, "CONSUMER_NAME": "Ramesh Patel",
                                          "signing_manifest": manifest, "doc_status": "complete"}))
        run(self.db.signing_submissions.insert_one({"token": "tok", "customer_id": str(self.cid)}))

    def _verify(self, folder):
        with FakeStorage(folder), mock.patch.object(signing, "get_db", lambda: self.db), \
                mock.patch.object(signing.settings, "R2_PRESIGNED_REVIEW", True):
            return run(signing.verify_token("tok"))["data"]["documents"]

    def test_review_gets_the_agreement_as_two_parts_when_stamped(self):
        docs = self._verify(FULL_FOLDER)
        self.assertTrue(docs[0]["url"])
        self.assertNotIn("parts", docs[0])
        # No `url`, so a page from before `parts` still streams the merged copy.
        self.assertIsNone(docs[1]["url"])
        self.assertEqual(docs[1]["parts"]["url"], fake_link(PREFIX + f"{NAME}_NP_Agreement.pdf", signing.REVIEW_LINK_SECONDS))
        self.assertEqual(docs[1]["parts"]["stamp_url"], fake_link(PREFIX + dg.NP_STAMP_UPLOAD_KEY, signing.REVIEW_LINK_SECONDS))

    def test_unstamped_agreement_is_a_plain_link(self):
        folder = [o for o in FULL_FOLDER if not o["key"].endswith(dg.NP_STAMP_UPLOAD_KEY)]
        docs = self._verify(folder)
        self.assertTrue(docs[1]["url"])
        self.assertNotIn("parts", docs[1])

    def test_signed_download_links_follow_the_same_rules_as_the_zip(self):
        with FakeStorage(FULL_FOLDER), mock.patch.object(signing, "get_db", lambda: self.db):
            with self.assertRaises(HTTPException) as unsigned:
                run(signing.signed_docs_links("tok"))
            self.assertEqual(unsigned.exception.status_code, 403)

            run(self.db.signing_submissions.update_one({"token": "tok"}, {"$set": {"submitted": True}}))
            run(self.db.customers.update_one({"_id": self.cid}, {"$set": {"doc_status": "generating"}}))
            with self.assertRaises(HTTPException) as busy:
                run(signing.signed_docs_links("tok"))
            self.assertEqual(busy.exception.status_code, 425)

            run(self.db.customers.update_one({"_id": self.cid}, {"$set": {"doc_status": "complete"}}))
            files = run(signing.signed_docs_links("tok"))["data"]["files"]
        self.assertEqual(len(files), 5)
        self.assertEqual(sum("stamp_url" in f for f in files), 1)


if __name__ == "__main__":
    unittest.main()
