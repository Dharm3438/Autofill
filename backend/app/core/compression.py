"""
Gzip for JSON and text answers only.

Render bills every byte the API sends out, and JSON shrinks 5-10x gzipped.
Starlette's own GZipMiddleware compresses every response, including PDFs and
zips that are already compressed (CPU spent for nothing, and a streamed file
loses its Content-Length). This one compresses only content types that gain
from it and passes everything else through untouched.
"""
import gzip

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

COMPRESSIBLE_TYPES = ("application/json", "text/")


def _compressible(headers: Headers) -> bool:
    if "content-encoding" in headers:
        return False
    content_type = headers.get("content-type", "").lower()
    return content_type.startswith(COMPRESSIBLE_TYPES)


class JSONGZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 1000, compresslevel: int = 6) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or "gzip" not in Headers(scope=scope).get("accept-encoding", ""):
            await self.app(scope, receive, send)
            return

        start: Message | None = None
        compress = False
        chunks: list[bytes] = []

        async def wrapped_send(message: Message) -> None:
            nonlocal start, compress
            if message["type"] == "http.response.start":
                start = message
                compress = _compressible(Headers(raw=message["headers"]))
                if not compress:
                    await send(message)
                return
            if message["type"] != "http.response.body" or not compress:
                await send(message)
                return

            # JSON answers are small and come in one piece; collect the body
            # (in case it is streamed) and compress it whole.
            chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return
            body = b"".join(chunks)
            headers = MutableHeaders(raw=start["headers"])
            if len(body) >= self.minimum_size:
                body = gzip.compress(body, compresslevel=self.compresslevel)
                headers["Content-Encoding"] = "gzip"
                headers.add_vary_header("Accept-Encoding")
            headers["Content-Length"] = str(len(body))
            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, wrapped_send)
