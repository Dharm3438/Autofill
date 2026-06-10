import { useState, useEffect, useRef } from 'react'
import { X, Upload, Check, Eye, Trash2, Loader2, Image, FileText, Stamp } from 'lucide-react'
import { getUploadStatus, uploadDocument, previewUpload, deleteUpload } from '../api/uploads'
import toast from 'react-hot-toast'

const SLOTS = [
  {
    kind: 'installation',
    title: 'Customer Installation Photo',
    hint: 'Upload one photo (JPG/PNG). Converted to PDF for the customer.',
    accept: 'image/png,image/jpeg',
    icon: Image,
  },
  {
    kind: 'np_stamp',
    title: 'Stamped NP Agreement First Page',
    hint: 'Print the first page on ₹100 stamp paper, then upload it back as a PDF.',
    accept: 'application/pdf',
    icon: Stamp,
  },
  {
    kind: 'dcr',
    title: 'DCR Document',
    hint: 'Upload the official DCR PDF downloaded from the government portal.',
    accept: 'application/pdf',
    icon: FileText,
  },
]

export default function UploadsModal({ customer, onClose, onChanged }) {
  const [status, setStatus] = useState({ installation: false, np_stamp: false, dcr: false })
  // Map of `${kind}:${action}` → true; each slot/action tracked independently
  const [busy, setBusy] = useState({})
  const fileRefs = useRef({})
  // Discard stale refresh responses when multiple uploads complete concurrently
  const refreshIdRef = useRef(0)

  async function refresh() {
    const id = ++refreshIdRef.current
    try {
      const res = await getUploadStatus(customer.id)
      if (id === refreshIdRef.current) setStatus(res.data.data)
    } catch {
      if (id === refreshIdRef.current) toast.error('Failed to load upload status')
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer.id])

  function handleClose() {
    // Notify the parent once, on close, so the customer list / Send-link gating
    // refreshes without unmounting this modal mid-upload.
    onChanged?.()
    onClose()
  }

  function setKey(key, active) {
    setBusy(prev => {
      const next = { ...prev }
      if (active) next[key] = true
      else delete next[key]
      return next
    })
  }

  async function handleFile(kind, file) {
    if (!file) return
    const key = `${kind}:upload`
    setKey(key, true)
    try {
      await uploadDocument(customer.id, kind, file)
      toast.success('Uploaded')
      await refresh()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed')
    } finally {
      setKey(key, false)
      if (fileRefs.current[kind]) fileRefs.current[kind].value = ''
    }
  }

  async function handleView(kind) {
    const key = `${kind}:view`
    setKey(key, true)
    try {
      const res = await previewUpload(customer.id, kind)
      const url = URL.createObjectURL(res.data)
      const win = window.open(url, '_blank')
      if (!win) toast.error('Allow pop-ups to preview the document')
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch {
      toast.error('Failed to open document')
    } finally {
      setKey(key, false)
    }
  }

  async function handleDelete(kind) {
    if (!confirm('Remove this uploaded document?')) return
    const key = `${kind}:delete`
    setKey(key, true)
    try {
      await deleteUpload(customer.id, kind)
      toast.success('Removed')
      await refresh()
    } catch {
      toast.error('Failed to remove document')
    } finally {
      setKey(key, false)
    }
  }

  const allDone = status.installation && status.np_stamp && status.dcr

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={handleClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Upload Documents</h2>
            <p className="text-sm text-gray-500 mt-0.5">{customer.CONSUMER_NAME}</p>
          </div>
          <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Slots */}
        <div className="p-6 space-y-4">
          {SLOTS.map(({ kind, title, hint, accept, icon: Icon }) => {
            const uploaded = status[kind]
            const isUploading = !!busy[`${kind}:upload`]
            const isViewing = !!busy[`${kind}:view`]
            const isDeleting = !!busy[`${kind}:delete`]
            return (
              <div
                key={kind}
                className={`rounded-xl border p-4 transition-colors ${uploaded ? 'border-emerald-200 bg-emerald-50/40' : 'border-gray-200 bg-gray-50/60'}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${uploaded ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                    {uploaded ? <Check className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-gray-800">{title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{hint}</p>

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <input
                        ref={(el) => (fileRefs.current[kind] = el)}
                        type="file"
                        accept={accept}
                        className="hidden"
                        onChange={(e) => handleFile(kind, e.target.files?.[0])}
                      />
                      <button
                        onClick={() => fileRefs.current[kind]?.click()}
                        disabled={isUploading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-50 transition-colors"
                      >
                        {isUploading
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Upload className="w-3.5 h-3.5" />}
                        {uploaded ? 'Replace' : 'Upload'}
                      </button>

                      {uploaded && (
                        <>
                          <button
                            onClick={() => handleView(kind)}
                            disabled={isViewing}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-600 hover:bg-white disabled:opacity-50 transition-colors"
                          >
                            {isViewing
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <Eye className="w-3.5 h-3.5" />}
                            View
                          </button>
                          <button
                            onClick={() => handleDelete(kind)}
                            disabled={isDeleting}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-red-500 hover:bg-red-50 disabled:opacity-50 transition-colors"
                          >
                            {isDeleting
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <Trash2 className="w-3.5 h-3.5" />}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
          <p className={`text-sm font-medium ${allDone ? 'text-emerald-600' : 'text-amber-600'}`}>
            {allDone ? 'All documents uploaded — ready to send signing link.' : 'All three required before sending the link.'}
          </p>
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm font-medium rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
