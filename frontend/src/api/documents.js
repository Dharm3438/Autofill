import api from './client'

export const generateDocs = (customerId) =>
  api.post(`/documents/generate/${customerId}`)

export const getDocStatus = (customerId) =>
  api.get(`/documents/status/${customerId}`)

export const listDocs = (customerId) =>
  api.get(`/documents/list/${customerId}`)

// Short-lived direct R2 links for the bundle (see utils/directDownload.js).
export const getBundleLinks = (customerId) =>
  api.get(`/documents/download/${customerId}/links`)

export const getNpFirstPageLink = (customerId) =>
  api.get(`/documents/download/${customerId}/np-first-page/link`)

// Server-built versions: the fallback if the direct R2 route fails.
export const downloadZip = (customerId) =>
  api.get(`/documents/download/${customerId}/zip`, { responseType: 'blob' })

export const downloadNpFirstPage = (customerId) =>
  api.get(`/documents/download/${customerId}/np-first-page`, { responseType: 'blob' })

export const sendSigningLink = (customerId) =>
  api.post(`/signing/send-link/${customerId}`)
