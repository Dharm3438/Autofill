"""
Bandwidth savings (Render bills every byte the API sends out). Run from backend/:

    python -m unittest discover -s tests -v

Covers: gzip for JSON only, the 2-hour CORS check cache, and the photo
shrinking for the installation photo and the Aadhaar images.
"""
import asyncio
import gzip
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

import fitz  # noqa: E402  (PyMuPDF)
from PIL import Image  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import Response, StreamingResponse  # noqa: E402

from app.core.compression import JSONGZipMiddleware  # noqa: E402
from app.routers.signing import AADHAAR_PHOTO_MAX_PX, _compress_photo  # noqa: E402
from app.routers.uploads import INSTALLATION_PHOTO_MAX_PX, _image_to_pdf  # noqa: E402


def call(app, method="GET", path="/", headers=None):
    """Run one request through an ASGI app; return (status, headers dict, body)."""
    scope = {
        "type": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "scheme": "http", "http_version": "1.1",
        "server": ("test", 80), "client": ("1.2.3.4", 1),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    sent = []
    requested = False

    async def receive():
        # The request body once; after that the client just stays connected
        # (a streamed response listens for a disconnect until it finishes).
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}, body


def _gzip_app():
    inner = FastAPI()

    @inner.get("/big")
    async def big():
        return {"rows": [{"name": f"Customer {i}", "city": "Surat"} for i in range(200)]}

    @inner.get("/small")
    async def small():
        return {"ok": True}

    @inner.get("/pdf")
    async def pdf():
        data = b"%PDF-1.4 " + b"x" * 5000
        return StreamingResponse(io.BytesIO(data), media_type="application/pdf")

    @inner.get("/zip")
    async def zip_():
        return Response(b"PK" + b"y" * 5000, media_type="application/zip")

    return JSONGZipMiddleware(inner, minimum_size=1000)


GZ = {"Accept-Encoding": "gzip, deflate, br"}


class JSONGzipTests(unittest.TestCase):
    def setUp(self):
        self.app = _gzip_app()

    def test_large_json_is_gzipped(self):
        status, headers, body = call(self.app, path="/big", headers=GZ)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-encoding"), "gzip")
        self.assertIn("Accept-Encoding", headers.get("vary", ""))
        self.assertEqual(int(headers["content-length"]), len(body))
        plain = gzip.decompress(body)
        self.assertIn(b"Customer 199", plain)
        self.assertLess(len(body), len(plain) / 4)

    def test_small_json_is_left_alone(self):
        _, headers, body = call(self.app, path="/small", headers=GZ)
        self.assertNotIn("content-encoding", headers)
        self.assertEqual(body, b'{"ok":true}')

    def test_no_gzip_without_accept_encoding(self):
        _, headers, body = call(self.app, path="/big")
        self.assertNotIn("content-encoding", headers)
        self.assertIn(b"Customer 199", body)

    def test_pdf_and_zip_pass_through_untouched(self):
        for path, magic in (("/pdf", b"%PDF"), ("/zip", b"PK")):
            _, headers, body = call(self.app, path=path, headers=GZ)
            self.assertNotIn("content-encoding", headers, path)
            self.assertTrue(body.startswith(magic), path)

    def test_real_app_gzips_json_and_caches_cors_check(self):
        from app.main import app
        # The keep-alive endpoint is tiny: answered as-is.
        _, headers, body = call(app, path="/health", headers=GZ)
        self.assertNotIn("content-encoding", headers)
        self.assertEqual(body, b'{"status":"ok"}')
        # The browser's CORS check is remembered for 2 hours.
        status, headers, _ = call(app, method="OPTIONS", path="/api/auth/me", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        })
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-max-age"), "7200")


def _photo(width, height, orientation=None) -> bytes:
    img = Image.effect_noise((width // 8, height // 8), 40).convert("RGB").resize((width, height))
    out = io.BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation  # 6 = the camera was turned; rotate 90° to view
        img.save(out, format="JPEG", quality=92, exif=exif)
    else:
        img.save(out, format="JPEG", quality=92)
    return out.getvalue()


class PhotoShrinkTests(unittest.TestCase):
    def test_installation_photo_pdf_is_capped_and_smaller(self):
        raw = _photo(4000, 3000)
        pdf = _image_to_pdf(raw)
        page = fitz.open(stream=pdf, filetype="pdf")[0]
        # Pillow writes the image at 72 dpi, so the page size in points = pixels.
        self.assertAlmostEqual(max(page.rect.width, page.rect.height), INSTALLATION_PHOTO_MAX_PX, delta=1)
        self.assertLess(len(pdf), len(raw) / 3)

    def test_installation_photo_follows_camera_rotation(self):
        pdf = _image_to_pdf(_photo(400, 200, orientation=6))
        page = fitz.open(stream=pdf, filetype="pdf")[0]
        self.assertGreater(page.rect.height, page.rect.width)

    def test_small_installation_photo_is_not_enlarged(self):
        page = fitz.open(stream=_image_to_pdf(_photo(800, 600)), filetype="pdf")[0]
        self.assertAlmostEqual(page.rect.width, 800, delta=1)

    def test_aadhaar_photo_is_capped(self):
        out = _compress_photo(_photo(4000, 3000))
        img = Image.open(io.BytesIO(out))
        self.assertEqual(img.format, "JPEG")
        self.assertEqual(max(img.size), AADHAAR_PHOTO_MAX_PX)

    def test_aadhaar_photo_follows_camera_rotation(self):
        img = Image.open(io.BytesIO(_compress_photo(_photo(400, 200, orientation=6))))
        self.assertEqual(img.size, (200, 400))


if __name__ == "__main__":
    unittest.main()
