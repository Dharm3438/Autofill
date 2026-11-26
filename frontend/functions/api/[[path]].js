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

// Render's free plan puts the backend to sleep when idle; waking it takes
// up to about a minute, and meanwhile Render answers with a gateway error
// instead of holding the request. Keep retrying for this long, so a request
// made during wake-up just takes longer instead of failing.
const WAKE_UP_WAIT_MS = 90_000
// Bodies up to this size are kept in memory so they can be re-sent on retry.
// Bigger uploads are streamed once and not retried.
const MAX_RETRY_BODY_BYTES = 10 * 1024 * 1024

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// A gateway error from Render's routing layer (backend asleep / starting /
// restarting), not an answer from our app. Our app always answers in JSON, so
// a JSON 502 (e.g. "couldn't send the email") is a real answer — never retried.
function isWakeUpError(response) {
  if (![502, 503, 504].includes(response.status)) return false
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
  for (;;) {
    attempt += 1
    let failure
    try {
      response = await fetch(target, { method: request.method, headers, body, redirect: 'manual' })
      if (!isWakeUpError(response)) break
      failure = `backend answered ${response.status}`
    } catch (err) {
      response = undefined
      failure = `fetch failed: ${err}`
    }
    // Visible in Cloudflare: Pages project > Functions > Real-time logs.
    console.error(`api proxy: ${request.method} ${incoming.pathname} attempt ${attempt} -> ${failure}`)
    if (!canRetry || Date.now() + wait > deadline) break
    await sleep(wait)
    wait = Math.min(wait * 1.5, 10_000)
  }

  if (!response || isWakeUpError(response)) {
    // Still not up. Answer in the backend's own {detail} format so the app
    // shows this instead of a misleading message.
    return Response.json(
      { detail: "The server is taking too long to start. Please try again in a minute." },
      { status: 503 },
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
