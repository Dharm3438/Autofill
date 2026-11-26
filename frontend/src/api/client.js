import axios from 'axios'

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

// Pages that work signed-out, where a 401 must not bounce to /login.
const PUBLIC_PATHS = ['/login', '/forgot-password', '/sign']

api.interceptors.response.use(
  (res) => res,
  (err) => {
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
