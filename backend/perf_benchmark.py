"""
Performance comparison harness for the optimizations in
`claude/performance-optimization-audit-aa3qky`.

Run:  python perf_benchmark.py

It does NOT touch MongoDB, R2, or Brevo. Network/disk latency is *simulated*
with sleeps using realistic round-trip times so the BEFORE/AFTER numbers are
reproducible on any machine. The ZIP benchmark uses real compression on
PDF-like (already-compressed) bytes, so those numbers are actual CPU time.

Tunables (override via env): RTT_R2_MS, EMAIL_MS, NUM_STALE_PDFS.
"""
import asyncio
import io
import os
import time
import zipfile
import secrets

RTT_R2_MS   = float(os.environ.get("RTT_R2_MS", 40))     # one R2 round trip
EMAIL_MS    = float(os.environ.get("EMAIL_MS", 800))     # Brevo send (typical)
NUM_STALE   = int(os.environ.get("NUM_STALE_PDFS", 7))   # PDFs from prior gen
R2 = RTT_R2_MS / 1000.0
EMAIL = EMAIL_MS / 1000.0


def banner(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


# ─────────────────────────────────────────────────────────────────────────────
# #1  Blocking email in the async event loop
#     Scenario: one user triggers send-link/OTP (a blocking requests.post),
#     while N other users hit any other endpoint at the same instant.
#     BEFORE: the email call blocks the loop -> everyone waits behind it.
#     AFTER:  asyncio.to_thread offloads it -> other requests fly through.
# ─────────────────────────────────────────────────────────────────────────────
async def bench_email_blocking():
    banner("#1  Email send blocking the event loop (9 bystander requests)")
    N = 9

    def blocking_email():
        time.sleep(EMAIL)            # sync requests.post(timeout=15)

    async def fast_request():
        await asyncio.sleep(0.005)   # a normal ~5ms endpoint
        return time.perf_counter()

    # BEFORE — sync call inside the coroutine blocks the single event loop.
    async def before():
        start = time.perf_counter()
        async def email_handler():
            blocking_email()         # <-- blocks the loop
        results = await asyncio.gather(email_handler(), *(fast_request() for _ in range(N)))
        finishes = [r for r in results if r is not None]
        worst = max(f - start for f in finishes)
        return worst

    # AFTER — email offloaded to a thread; bystanders are unaffected.
    async def after():
        start = time.perf_counter()
        async def email_handler():
            await asyncio.to_thread(blocking_email)
        results = await asyncio.gather(email_handler(), *(fast_request() for _ in range(N)))
        finishes = [r for r in results if r is not None]
        worst = max(f - start for f in finishes)
        return worst

    b = await before()
    a = await after()
    print(f"  EMAIL_MS={EMAIL_MS:.0f}, bystanders={N}")
    print(f"  BEFORE  worst bystander latency : {b*1000:8.1f} ms  (stuck behind the email)")
    print(f"  AFTER   worst bystander latency : {a*1000:8.1f} ms")
    print(f"  -> bystander requests {b/a:5.1f}x faster; event loop no longer frozen")


# ─────────────────────────────────────────────────────────────────────────────
# #5  Doc-gen image fetch: 4 images, HEAD+GET serial  ->  GET-only parallel
# ─────────────────────────────────────────────────────────────────────────────
async def bench_image_fetch():
    banner("#5  Signing image fetch from R2 (signature, photo, aadhar x2)")

    async def head():  await asyncio.sleep(R2)
    async def get():   await asyncio.sleep(R2)

    # BEFORE: for each of 4 images -> object_exists (HEAD) then download (GET),
    # all sequential.
    async def before():
        start = time.perf_counter()
        for _ in range(4):
            await head()
            await get()
        return time.perf_counter() - start

    # AFTER: skip HEAD, GET only, all 4 concurrently.
    async def after():
        start = time.perf_counter()
        await asyncio.gather(*(get() for _ in range(4)))
        return time.perf_counter() - start

    b = await before()
    a = await after()
    print(f"  RTT_R2_MS={RTT_R2_MS:.0f}")
    print(f"  BEFORE  8 serial round trips : {b*1000:8.1f} ms")
    print(f"  AFTER   4 parallel GETs      : {a*1000:8.1f} ms")
    print(f"  -> {b/a:5.1f}x faster")


# ─────────────────────────────────────────────────────────────────────────────
# #6  Stale PDF cleanup: per-key LIST+DELETE  ->  one batched delete_objects
# ─────────────────────────────────────────────────────────────────────────────
async def bench_stale_delete():
    banner(f"#6  Deleting {NUM_STALE} stale PDFs before regeneration")

    async def list_call():   await asyncio.sleep(R2)
    async def delete_call(): await asyncio.sleep(R2)

    # BEFORE: one initial list, then delete_prefix(key) per key — and each
    # delete_prefix does its OWN list + delete. Serial.
    async def before():
        start = time.perf_counter()
        await list_call()                      # initial listing
        for _ in range(NUM_STALE):
            await list_call()                  # delete_prefix re-lists
            await delete_call()
        return time.perf_counter() - start

    # AFTER: one initial list, then a single batched delete_keys call.
    async def after():
        start = time.perf_counter()
        await list_call()                      # initial listing
        await delete_call()                    # one delete_objects batch
        return time.perf_counter() - start

    b = await before()
    a = await after()
    before_calls = 1 + NUM_STALE * 2
    print(f"  RTT_R2_MS={RTT_R2_MS:.0f}")
    print(f"  BEFORE  {before_calls:2d} round trips : {b*1000:8.1f} ms")
    print(f"  AFTER    2 round trips : {a*1000:8.1f} ms")
    print(f"  -> {b/a:5.1f}x faster")


# ─────────────────────────────────────────────────────────────────────────────
# #7  ZIP of the delivered bundle: DEFLATE -> STORED on already-compressed PDFs
#     Real CPU work on representative (incompressible) data.
# ─────────────────────────────────────────────────────────────────────────────
def bench_zip():
    banner("#7  Zipping the document bundle (PDF-like / already-compressed data)")
    # ~9 docs averaging ~1.5 MB each, like a real customer bundle. PDFs barely
    # compress, so we use random bytes to represent their (incompressible) body.
    bundle = [(f"doc_{i}.pdf", secrets.token_bytes(1_500_000)) for i in range(9)]
    total_in = sum(len(d) for _, d in bundle)

    def zip_with(method):
        start = time.perf_counter()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", method) as zf:
            for name, data in bundle:
                zf.writestr(name, data)
        return time.perf_counter() - start, buf.getbuffer().nbytes

    # warm up allocator
    zip_with(zipfile.ZIP_STORED)

    t_def, sz_def = zip_with(zipfile.ZIP_DEFLATED)
    t_sto, sz_sto = zip_with(zipfile.ZIP_STORED)
    print(f"  bundle: {len(bundle)} files, {total_in/1e6:.1f} MB total")
    print(f"  BEFORE  ZIP_DEFLATED : {t_def*1000:8.1f} ms   -> {sz_def/1e6:5.2f} MB")
    print(f"  AFTER   ZIP_STORED   : {t_sto*1000:8.1f} ms   -> {sz_sto/1e6:5.2f} MB")
    print(f"  -> {t_def/t_sto:5.1f}x faster CPU; size diff {(sz_def-sz_sto)/1e6:+.2f} MB "
          f"(~{100*(sz_def-sz_sto)/sz_def:+.1f}%)")
    print("  (and this CPU now runs off the event loop via asyncio.to_thread)")


# ─────────────────────────────────────────────────────────────────────────────
# #2  Debounced search — request count for typing a query
# ─────────────────────────────────────────────────────────────────────────────
def bench_debounce():
    banner("#2  Search requests while typing (debounce, frontend)")
    query = "Sharma"   # 6 keystrokes
    before = len(query)   # one request per keystroke
    after = 1             # one request once typing settles (350ms)
    print(f"  typing '{query}' ({len(query)} keystrokes)")
    print(f"  BEFORE  backend requests : {before}  (each = an unindexed regex scan)")
    print(f"  AFTER   backend requests : {after}")
    print(f"  -> {before}x fewer requests / DB scans per search")


async def main():
    print("Perf comparison — BEFORE vs AFTER (latencies simulated, ZIP is real CPU)")
    await bench_email_blocking()
    await bench_image_fetch()
    await bench_stale_delete()
    bench_zip()
    bench_debounce()
    print("\nDone. Tune with RTT_R2_MS / EMAIL_MS / NUM_STALE_PDFS env vars.\n")


if __name__ == "__main__":
    asyncio.run(main())
