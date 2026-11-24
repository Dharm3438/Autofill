import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api` : '/api',
  withCredentials: true,
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const path = window.location.pathname
    if (err.response?.status === 401 && !path.includes('/login') && !path.includes('/sign')) {
      window.location.href = '/login'
    }
    // 403 means the page is out of date with the user's access (e.g. an admin
    // just changed their roles). Reload from "/" so the app re-reads /auth/me
    // and routes them to the right landing page.
    if (err.response?.status === 403 && !path.includes('/login') && !path.includes('/sign') && !path.includes('/welcome')) {
      window.location.href = '/'
    }
    return Promise.reject(err)
  }
)

export default api
