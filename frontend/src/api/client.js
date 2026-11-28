import axios from 'axios'
import { clearToken, getToken, setToken } from './token'
import { trackRequest } from './slowRequests'

// Production calls the backend on Render directly (VITE_API_URL, required at
// build time — see vite.config.js). In development VITE_API_URL is usually
// unset and vite.config.js proxies /api to the local backend.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL.replace(/\/$/, '')}/api` : '/api',
})

// Pages that work signed-out, where a 401 must not bounce to /login.
const PUBLIC_PATHS = ['/login', '/forgot-password', '/sign']

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  config._stopTracking = trackRequest()
  return config
})

api.interceptors.response.use(
  (res) => {
    res.config._stopTracking?.()
    // Login, sign-up and password change answer with a fresh token.
    if (typeof res.data?.access_token === 'string') setToken(res.data.access_token)
    return res
  },
  (err) => {
    err.config?._stopTracking?.()
    const path = window.location.pathname
    const isPublic = PUBLIC_PATHS.some((p) => path.startsWith(p))
    if (err.response?.status === 401) {
      // The token is missing, expired or was signed out elsewhere.
      if (err.config?.headers?.Authorization) clearToken()
      if (!isPublic) window.location.href = '/login'
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
