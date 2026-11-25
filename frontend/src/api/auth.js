import api from './client'

// `identifier` is an email or a username.
export const login = (identifier, password) =>
  api.post('/auth/login', { identifier, password })

export const logout = () =>
  api.post('/auth/logout')

export const logoutAll = () =>
  api.post('/auth/logout-all')

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
