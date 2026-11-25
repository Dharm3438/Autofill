import api from './client'

export const getUsers = () =>
  api.get('/users')

// body: { roles?: string[], is_active?: boolean, email?: string, username?: string }
// Changing the email marks it unverified (the user re-verifies from Account).
export const updateUserAccess = (id, body) =>
  api.put(`/users/${id}`, body)
