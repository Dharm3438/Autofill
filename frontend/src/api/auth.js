import api from './client'
import { clearToken } from './token'

// `identifier` is an email or a username.
// The token in a successful answer is saved by api/client.js.
export const login = (identifier, password) =>
  api.post('/auth/login', { identifier, password })

// Signing out = forgetting the token on this device (even if the request fails).
export const logout = () =>
  api.post('/auth/logout').finally(clearToken)

// Makes every existing token stop working, this device's included.
export const logoutAll = () =>
  api.post('/auth/logout-all').then((res) => {
    clearToken()
    return res
  })

export const getMe = () =>
  api.get('/auth/me')

// Sign-up is two steps: send a code (no account yet), then confirm it.
// Calling register again with the same email re-sends a fresh code.
export const register = ({ name, username, email, password }) =>
  api.post('/auth/register', { name, username, email, password })

export const verifyRegistration = (email, code) =>
  api.post('/auth/register/verify', { email, code })

export const forgotPassword = (identifier) =>
  api.post('/auth/forgot-password', { identifier })

export const resetPassword = (identifier, code, password) =>
  api.post('/auth/reset-password', { identifier, code, password })

export const changePassword = (current_password, new_password) =>
  api.post('/auth/change-password', { current_password, new_password })

export const setUsername = (username) =>
  api.put('/auth/me/username', { username })

// Sends a code to `email` (a new address, or the current one to verify it).
export const startEmailChange = (email, password) =>
  api.post('/auth/me/email', { email, password })

export const confirmEmailChange = (code) =>
  api.post('/auth/me/email/confirm', { code })
