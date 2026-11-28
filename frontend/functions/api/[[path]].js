// Cloudflare Pages Function: forwards every /api/* request to the backend on
// Render, so the browser only ever talks to the frontend's own domain.
//
// Why: the login cookie must be first-party. When the app called the Render
// domain directly, Safari and private/incognito windows treated the cookie as
// a third-party cookie and threw it away, so people landed back on the login
// screen right after signing in. (Pages' _redirects can't proxy to another
// domain, hence this function.)
//
// The backend URL can be overridden with a BACKEND_URL environment variable in
// the Pages project settings; otherwise the default below is used.

const DEFAULT_BACKEND = 'https://autofill-blgf.onrender.com'

// Render's free plan puts the backend to sleep after ~15 idle minutes. Waking
// it (starting a large Docker image on a tiny CPU share) can take 1-3 minutes,
// and meanwhile Render answers with gateway errors or holds the request. Keep
// retrying for this long, so a request made during wake-up just takes longer
// instead of failing. (90s was too short: cold starts often ran past it.)
// If it still isn't up, the app itself keeps waiting and retries
// (frontend/src/api/serverWake.js), so this is not the last line of defence.
const WAKE_UP_WAIT_MS = 180_000
// Bodies up to this size are kept in memory so they can be re-sent on retry.
// Bigger uploads are streamed once and not retried.
const MAX_RETRY_BODY_BYTES = 10 * 1024 * 1024

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Gateway errors that mean "the backend isn't answering yet": Render's own
// 502/503/504 while it starts, Cloudflare's 52x/530 from the edge in front of
// Render (e.g. 524 when Render held the request for 100s, 522/523 when it
// couldn't connect), and 429 from that edge (it rate-limits requests to a
// service that's starting up — this was the "Too many attempts" people saw on
// the first sign-in after a quiet spell). Our app always answers in JSON, so a
// JSON 5xx or 429 (e.g. our own sign-in lockout) is a real answer and is never
// retried.
const WAKE_UP_STATUSES = new Set([429, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530])
const MAX_RETRY_AFTER_MS = 15_000

function isWakeUpError(response) {
  if (!WAKE_UP_STATUSES.has(response.status)) return false
  return !(response.headers.get('content-type') || '').includes('application/json')
}

export async function onRequest({ request, env }) {
  const backend = new URL(env.BACKEND_URL || DEFAULT_BACKEND)
  const incoming = new URL(request.url)
  const target = new URL(incoming.pathname + incoming.search, backend)

  const headers = new Headers(request.headers)
  // Let fetch set Host for the backend, and don't pass Cloudflare's own
  // per-hop headers on to another Cloudflare-fronted site (Render).
  headers.delete('host')
  for (const name of [...headers.keys()]) {
    if (name.startsWith('cf-')) headers.delete(name)
  }
  // The real visitor's IP, set by Cloudflare (clients can't forge it). The
  // backend's rate limits find it by counting back past Render's own entries
  // (TRUSTED_PROXY_HOPS in backend/app/core/config.py).
  const clientIp = request.headers.get('cf-connecting-ip')
  if (clientIp) headers.set('x-forwarded-for', clientIp)
  else headers.delete('x-forwarded-for')

  const hasBody = !['GET', 'HEAD'].includes(request.method)
  // Unknown length (streamed upload) or too big: send once, no retry.
  const length = request.headers.get('content-length')
  const canRetry = !hasBody || (length !== null && Number(length) <= MAX_RETRY_BODY_BYTES)
  // Read a small body once so every attempt can send the same bytes.
  const body = !hasBody ? undefined : canRetry ? await request.arrayBuffer() : request.body

  const deadline = Date.now() + WAKE_UP_WAIT_MS
  let wait = 2000
  let attempt = 0
  let response
  let lastUpstream = null // what Render last answered, for the give-up reply
  for (;;) {
    attempt += 1
    let failure
    try {
      response = await fetch(target, { method: request.method, headers, body, redirect: 'manual' })
      if (!isWakeUpError(response)) break
      // Which edge answered: Render's routing header / Cloudflare's ray id.
      const via = ['x-render-routing', 'server', 'cf-ray']
        .map((h) => response.headers.get(h) && `${h}=${response.headers.get(h)}`).filter(Boolean).join(' ')
      failure = `backend answered ${response.status}${via ? ` (${via})` : ''}`
      lastUpstream = { status: response.status, via }
    } catch (err) {
      response = undefined
      failure = `fetch failed: ${err}`
    }
    // Visible in Cloudflare: Pages project > Functions > Real-time logs.
    console.error(`api proxy: ${request.method} ${incoming.pathname} attempt ${attempt} -> ${failure}`)
    // Honour the edge's Retry-After (seconds) when it gives one, within reason.
    const retryAfter = Number(response?.headers.get('retry-after'))
    // A 429 means "slow down": re-asking every couple of seconds can keep us
    // throttled, so wait at least 5s after one.
    const floor = response?.status === 429 ? Math.max(wait, 5_000) : wait
    const pause = retryAfter > 0 ? Math.min(Math.max(retryAfter * 1000, floor), MAX_RETRY_AFTER_MS) : floor
    if (!canRetry || Date.now() + pause > deadline) break
    await sleep(pause)
    wait = Math.min(wait * 1.5, 10_000)
  }

  if (!response || isWakeUpError(response)) {
    // Still not up. Answer in the backend's own {detail} format, marked so the
    // app knows the server is still waking (it then keeps waiting and retries
    // by itself; Idempotency-Key keeps a retried write from running twice).
    return Response.json(
      // `upstream` says what Render last answered (status + its routing headers):
      // visible in the browser's network tab, for diagnosing a server that won't wake.
      { detail: 'The server is still starting up. Please wait a moment.', code: 'server_waking', upstream: lastUpstream },
      { status: 503, headers: { 'x-server-waking': '1', 'retry-after': '5' } },
    )
  }

  // A redirect from the backend (e.g. a trailing-slash fix) would point at the
  // Render domain; keep the browser on ours.
  const location = response.headers.get('location')
  if (location) {
    const loc = new URL(location, target)
    if (loc.origin === backend.origin) {
      const out = new Response(response.body, response)
      out.headers.set('location', incoming.origin + loc.pathname + loc.search)
      return out
    }
  }
  return response
}
