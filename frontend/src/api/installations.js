import api from './client'

// params: { search, status, pending_step, dealer, page, limit } — one page,
// sorted by completion then name. Pass { all: true } instead of page/limit to
// get every filtered row (used by Print).
export const getInstallationOverview = (params) =>
  api.get('/installations/overview', { params })

export const getInstallation = (customerId) =>
  api.get(`/installations/${customerId}`)

// data: { status, completed_date, performed_by } (all optional)
export const updateInstallationStep = (customerId, stepKey, data) =>
  api.put(`/installations/${customerId}/steps/${stepKey}`, data)

// data: { received_payments: [{ amount, date }] }
export const updateInstallationPayment = (customerId, data) =>
  api.put(`/installations/${customerId}/payment`, data)

// data: { INVERTER_SR_NO, PANEL_SR_NO } — equipment data only.
// Installation date is derived from the Inverter / Solar Panel Installation
// checklist steps, not from serials.
export const updateInstallationSerials = (customerId, data) =>
  api.put(`/installations/${customerId}/serials`, data)

// Save a step group (e.g. wiring) at once: which members are done, plus the
// single completed date and "done by" shared by all done members.
// data: { done_keys: string[], completed_date, performed_by }
export const updateInstallationGroup = (customerId, groupKey, data) =>
  api.put(`/installations/${customerId}/groups/${groupKey}`, data)
