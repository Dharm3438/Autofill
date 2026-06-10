import api from './client'

// kind: 'installation' | 'np_stamp' | 'dcr'
const ENDPOINT = {
  installation: 'installation',
  np_stamp: 'np-stamp',
  dcr: 'dcr',
}

export const getUploadStatus = (customerId) =>
  api.get(`/uploads/${customerId}`)

export const uploadDocument = (customerId, kind, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/uploads/${customerId}/${ENDPOINT[kind]}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const previewUpload = (customerId, kind) =>
  api.get(`/uploads/${customerId}/${kind}`, { responseType: 'blob' })

export const deleteUpload = (customerId, kind) =>
  api.delete(`/uploads/${customerId}/${kind}`)
