// Keeps the app working while the backend wakes up.
//
// Render's free plan puts the backend to sleep after ~15 idle minutes, and
// waking it takes 1-3 minutes. Without this, whatever the user did first after
// a break (signing in, opening a page, saving, uploading) failed, and a failed
// /auth/me looked like "not signed in" and sent them to the login screen.
//
// What happens instead:
//   1. A request that fails because the server isn't answering (no response at
//      all, a gateway error page, or the /api proxy's own "still waking" 503)
//      is NOT shown as an error. The app marks the server as waking — a banner
//      says "Connecting to the server…" — polls /health until it answers, then
//      re-sends the request. Writes keep their Idempotency-Key, so a re-sent
//      write runs only once on the backend (backend/app/core/idempotency.py).
//   2. A request that is merely slow (the /api proxy holds it while the server
//      starts) triggers a quick /health check; if that doesn't answer either,
//      the banner shows, so a long wait never looks like a frozen screen.
//   3. While the server is waking, new requests wait for it instead of piling up.
//   4. Coming back to the tab after a while pings /health, so the server starts
//      waking before the first click.
// A request only gives up after MAX_WAIT_MS of waiting; the error then says
// the server couldn't be reached (never "wrong password" or similar).

export const MAX_WAIT_MS = 5 * 60_000       // per request, from its first failure
const SLOW_REQUEST_MS = 3_000               // a request this slow gets a health check
const QUICK_CHECK_MS = 3_000                // an awake server answers /health well within this
const HEALTH_ATTEMPT_MS = 200_000           // the /api proxy itself waits up to 180s
const POLL_GAP_MS = 3_000
const AWAY_PING_MS = 5 * 60_000             // tab hidden this long → ping on return

// Gateway errors (Render while starting, Cloudflare's edge in front of it).
const WAKE_STATUSES = new Set([502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530])

let healthUrl = '/api/health'
let status = 'ok'                           // 'ok' | 'waking'
let wakingSince = null
let poller = null                           // Promise while polling /health
const listeners = new Set()

export function configureServerWake({ baseURL }) {
  healthUrl = `${(baseURL || '/api').replace(/\/$/, '')}/health`
}

export function getServerStatus() {
  return { status, since: wakingSince }
}

export function subscribeServerStatus(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function setStatus(next) {
  if (next === status) return
  status = next
  wakingSince = next === 'waking' ? Date.now() : null
  listeners.forEach((fn) => fn(getServerStatus()))
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function header(response, name) {
  const h = response?.headers
  if (!h) return undefined
  return typeof h.get === 'function' ? h.get(name) : h[name]
}

// True when an axios error means "the server isn't answering yet" — as opposed
// to a real answer from our backend (wrong password, validation error, 500 …).
export function isServerUnavailable(err) {
  if (!err || err.code === 'ERR_CANCELED' || err.name === 'CanceledError') return false
  const res = err.response
  if (!res) return true // network error, timeout, or a gateway page without CORS headers
  if (header(res, 'x-server-waking') || res.data?.code === 'server_waking') return true
  if (!WAKE_STATUSES.has(res.status)) return false
  // Our backend always answers in JSON; a JSON 502/503 is a real answer.
  return !String(header(res, 'content-type') || '').includes('application/json')
}

async function healthOk(timeoutMs) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(healthUrl, { cache: 'no-store', credentials: 'omit', signal: ctrl.signal })
    if (!res.ok) return false
    const body = await res.json().catch(() => null)
    return body?.status === 'ok'
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

// Resolves once /health answers. One shared poller, however many requests wait.
export function waitForServer() {
  if (!poller) {
    setStatus('waking')
    poller = (async () => {
      for (;;) {
        if (await healthOk(HEALTH_ATTEMPT_MS)) break
        await sleep(POLL_GAP_MS)
      }
      setStatus('ok')
      poller = null
    })()
  }
  return poller
}

// Waits for the server, but no longer than `ms`. Resolves true if it's up.
export async function waitForServerUpTo(ms) {
  if (ms <= 0) return false
  let timer
  const up = await Promise.race([
    waitForServer().then(() => true),
    new Promise((resolve) => { timer = setTimeout(() => resolve(false), ms) }),
  ])
  clearTimeout(timer)
  return up
}

export function isWaking() {
  return status === 'waking'
}

// Quick check used when a request is slow or the tab comes back: if /health
// doesn't answer promptly, the server is asleep → show the banner and poll.
let checking = false
export async function checkServer() {
  if (checking || poller) return
  checking = true
  try {
    if (!(await healthOk(QUICK_CHECK_MS))) waitForServer()
  } finally {
    checking = false
  }
}

// Called for every request: starts a timer that checks the server if the
// request is still pending after SLOW_REQUEST_MS. Returns a function to stop it.
export function watchSlowRequest() {
  const timer = setTimeout(checkServer, SLOW_REQUEST_MS)
  return () => clearTimeout(timer)
}

// Wake the server when the user returns to a tab that was hidden for a while.
if (typeof document !== 'undefined') {
  let hiddenAt = null
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      hiddenAt = Date.now()
    } else if (hiddenAt && Date.now() - hiddenAt >= AWAY_PING_MS) {
      hiddenAt = null
      checkServer()
    }
  })
}
