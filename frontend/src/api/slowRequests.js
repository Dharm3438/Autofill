// Tracks requests that are taking a long time, so the app can explain the wait.
//
// Render's free plan puts the backend to sleep when idle. The first request
// after a break is held by Render while the server starts (often 30-90 seconds)
// and then answered normally — nothing is retried or re-sent. This only lets
// ServerStatusBanner say "the server is starting" instead of looking frozen.

const SLOW_MS = 5_000

let slowCount = 0
let slowSince = null
const listeners = new Set()

function emit() {
  listeners.forEach((fn) => fn(getSlowState()))
}

export function getSlowState() {
  return { slow: slowCount > 0, since: slowSince }
}

export function subscribeSlowRequests(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

// Call when a request starts; call the returned function when it ends.
export function trackRequest() {
  let counted = false
  const timer = setTimeout(() => {
    counted = true
    if (slowCount++ === 0) slowSince = Date.now()
    emit()
  }, SLOW_MS)
  return () => {
    clearTimeout(timer)
    if (!counted) return
    counted = false
    if (--slowCount === 0) slowSince = null
    emit()
  }
}
