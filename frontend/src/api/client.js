import axios from 'axios'
import {
  MAX_WAIT_MS, configureServerWake, isServerUnavailable, isWaking, waitForServerUpTo, watchSlowRequest,
} from './serverWake'

// Always same-origin. The browser never talks to the backend's own domain:
// in production the Cloudflare Pages Function functions/api/[[path]].js
// forwards it to Render, in dev vite.config.js does.
// That keeps the login cookie first-party — Safari and private/incognito
// windows throw away cookies set by another site (a third-party cookie), which
// used to bounce people straight back to the login screen after signing in.
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
})

configureServerWake({ baseURL: api.defaults.baseURL })

// Pages that work signed-out, where a 401 must not bounce to /login.
const PUBLIC_PATHS = ['/login', '/forgot-password', '/sign']

const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete'])

// Retries of one request while the server wakes. The pause grows so a request
// that keeps failing while /health is fine (e.g. it crashes the server) can't
// loop tightly; the 5-minute limit (MAX_WAIT_MS) still applies on top.
const RETRY_PAUSES_MS = [500, 2_000, 5_000, 10_000, 10_000, 10_000, 15_000, 15_000]
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
}

api.interceptors.request.use(async (config) => {
  // One key per user action, kept on every retry of it (the proxy's and ours),
  // so the backend runs a write once however many times it arrives.
  if (UNSAFE_METHODS.has((config.method || 'get').toLowerCase()) && !config.headers['Idempotency-Key']) {
    config.headers['Idempotency-Key'] = newIdempotencyKey()
  }
  // Server known to be waking: wait for it rather than adding to the pile.
  if (isWaking()) {
    config._wakeStart ??= Date.now()
    await waitForServerUpTo(MAX_WAIT_MS - (Date.now() - config._wakeStart))
  }
  config._stopSlowWatch?.()
  config._stopSlowWatch = watchSlowRequest()
  return config
})

api.interceptors.response.use(
  (res) => {
    res.config._stopSlowWatch?.()
    return res
  },
  async (err) => {
    const config = err.config
    config?._stopSlowWatch?.()

    // The server isn't answering (asleep / starting / restarting): wait for it
    // and send the same request again, instead of failing.
    if (config && isServerUnavailable(err)) {
      config._wakeStart ??= Date.now()
      const attempt = config._wakeRetries = (config._wakeRetries || 0) + 1
      const left = MAX_WAIT_MS - (Date.now() - config._wakeStart)
      if (left > 0 && attempt <= RETRY_PAUSES_MS.length) {
        await waitForServerUpTo(left)
        await sleep(RETRY_PAUSES_MS[attempt - 1])
        return api.request(config)
      }
      err.serverUnavailable = true
      return Promise.reject(err)
    }

    const path = window.location.pathname
    const isPublic = PUBLIC_PATHS.some((p) => path.startsWith(p))
    if (err.response?.status === 401 && !isPublic) {
      window.location.href = '/login'
    }
    // 403 means the page is out of date with the user's access (e.g. an admin
    // just changed their roles). Reload from "/" so the app re-reads /auth/me
    // and routes them to the right landing page.
    if (err.response?.status === 403 && !isPublic && !path.startsWith('/welcome') && !path.startsWith('/account')) {
      window.location.href = '/'
    }
    return Promise.reject(err)
  }
)

export default api
