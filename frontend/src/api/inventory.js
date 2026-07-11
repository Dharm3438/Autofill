import api from './client'

// Aggregated required-vs-available view for every equipment combination.
export const getInventoryOverview = () => api.get('/inventory/overview')

// data: { category, company, spec, stock } — set the on-hand base stock.
export const setInventoryStock = (data) => api.put('/inventory/stock', data)
