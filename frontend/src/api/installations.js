import api from './client'

// params: { search, status, pending_step, dealer }
export const getInstallationOverview = (params) =>
  api.get('/installations/overview', { params })

export const getInstallation = (customerId) =>
  api.get(`/installations/${customerId}`)

// data: { status, completed_date, performed_by, notes } (all optional)
export const updateInstallationStep = (customerId, stepKey, data) =>
  api.put(`/installations/${customerId}/steps/${stepKey}`, data)

// data: { received_payments: [{ amount, date }] }
export const updateInstallationPayment = (customerId, data) =>
  api.put(`/installations/${customerId}/payment`, data)

// data: { INVERTER_SR_NO, PANEL_SR_NO }
// Installation date is derived server-side from when both serials were filled.
export const updateInstallationSerials = (customerId, data) =>
  api.put(`/installations/${customerId}/serials`, data)
