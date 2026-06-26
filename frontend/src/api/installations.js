import api from './client'

// params: { search, status, pending_step }
export const getInstallationOverview = (params) =>
  api.get('/installations/overview', { params })

export const getInstallation = (customerId) =>
  api.get(`/installations/${customerId}`)

// data: { status, completed_date, performed_by, notes } (all optional)
export const updateInstallationStep = (customerId, stepKey, data) =>
  api.put(`/installations/${customerId}/steps/${stepKey}`, data)

// data: { total_payment, received_payment }
export const updateInstallationPayment = (customerId, data) =>
  api.put(`/installations/${customerId}/payment`, data)
