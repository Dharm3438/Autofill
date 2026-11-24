import api from './client'

export const getUsers = () =>
  api.get('/users')

// body: { roles?: string[], is_active?: boolean }
export const updateUserAccess = (id, body) =>
  api.put(`/users/${id}`, body)
