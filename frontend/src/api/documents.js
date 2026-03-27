import api from './client'

export const generateDocs = (customerId) =>
  api.post(`/documents/generate/${customerId}`)

export const getDocStatus = (customerId) =>
  api.get(`/documents/status/${customerId}`)

export const listDocs = (customerId) =>
  api.get(`/documents/list/${customerId}`)

export const downloadZip = (customerId) =>
  api.get(`/documents/download/${customerId}/zip`, { responseType: 'blob' })

export const sendSigningLink = (customerId) =>
  api.post(`/signing/send-link/${customerId}`)
