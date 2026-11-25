import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api` : '/api',
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
