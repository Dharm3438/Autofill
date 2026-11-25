import api from './client'

// Every dealer / equipment option list (inactive items included, flagged).
export const getCatalog = () => api.get('/catalog')

// body: { type, value, warranty? } — admin only.
export const addCatalogItem = (body) => api.post('/catalog', body)

// body: { warranty?, active? } — admin only. Values can't be renamed.
export const updateCatalogItem = (id, body) => api.put(`/catalog/${id}`, body)
