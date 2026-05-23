import { useState, useEffect, useRef } from 'react'
import { Pencil, Trash2, FileText, Send, Download, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { deleteCustomer } from '../api/customers'
import { generateDocs, getDocStatus, sendSigningLink, downloadZip } from '../api/documents'
import toast from 'react-hot-toast'

const DOC_STATUS_STYLES = {
  none:       'bg-gray-100 text-gray-500 border border-gray-200',
  generating: 'bg-amber-50 text-amber-700 border border-amber-200',
  complete:   'bg-emerald-50 text-emerald-700 border border-emerald-200',
  failed:     'bg-red-50 text-red-600 border border-red-200',
}

const SIGN_STATUS_STYLES = {
  none:   'bg-gray-100 text-gray-500 border border-gray-200',
  sent:   'bg-blue-50 text-blue-700 border border-blue-200',
  signed: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
}

const STATUS_LABELS = {
  none:       'Not Generated',
  generating: 'Generating…',
  complete:   'Complete',
  failed:     'Failed',
  sent:       'Link Sent',
  signed:     'Signed',
}

export default function CustomerTable({ customers, onEdit, onRefresh }) {
  const [expanded, setExpanded]   = useState(null)
  const [loadingId, setLoadingId] = useState(null)
  const pollingRef = useRef({})

  useEffect(() => {
    const generating = customers.filter(c => c.doc_status === 'generating')
    generating.forEach(c => {
      if (pollingRef.current[c.id]) return
      pollingRef.current[c.id] = setInterval(async () => {
        try {
          const res = await getDocStatus(c.id)
          const status = res.data.data.doc_status
          if (status !== 'generating') {
            clearInterval(pollingRef.current[c.id])
            delete pollingRef.current[c.id]
            onRefresh()
            if (status === 'complete') toast.success(`Docs ready for ${c.CONSUMER_NAME}`)
            if (status === 'failed')   toast.error(`Doc generation failed for ${c.CONSUMER_NAME}`)
          }
        } catch {
          clearInterval(pollingRef.current[c.id])
          delete pollingRef.current[c.id]
        }
      }, 3000)
    })

    return () => {
      const generatingIds = new Set(generating.map(c => c.id))
      Object.keys(pollingRef.current).forEach(id => {
        if (!generatingIds.has(id)) {
          clearInterval(pollingRef.current[id])
          delete pollingRef.current[id]
        }
      })
    }
  }, [customers, onRefresh])

  async function handleDelete(customer) {
    if (!confirm(`Delete ${customer.CONSUMER_NAME}? This cannot be undone.`)) return
    try {
      await deleteCustomer(customer.id)
      toast.success('Customer deleted')
      onRefresh()
    } catch {
      toast.error('Failed to delete customer')
    }
  }

  async function handleGenerateDocs(customer) {
    setLoadingId(`gen-${customer.id}`)
    try {
      await generateDocs(customer.id)
      toast.success('Document generation started')
      onRefresh()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start generation')
    } finally {
      setLoadingId(null)
    }
  }

  async function handleSendLink(customer) {
    if (!customer.CONSUMER_EMAIL) {
      toast.error('Customer has no email address')
      return
    }
    setLoadingId(`send-${customer.id}`)
    try {
      await sendSigningLink(customer.id)
      toast.success('Signing link sent to customer')
      onRefresh()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send link')
    } finally {
      setLoadingId(null)
    }
  }

  async function handleDownload(customer) {
    setLoadingId(`dl-${customer.id}`)
    try {
      const res = await downloadZip(customer.id)
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${customer.CONSUMER_NAME}_documents.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Failed to download documents')
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b-2 border-gray-100">
            <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
            <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">App No</th>
            <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Phone</th>
            <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Docs</th>
            <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Signing</th>
            <th className="text-right px-5 py-3.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {customers.map((c) => (
            <>
              <tr
                key={c.id}
                className={`hover:bg-[#f0f7f3] transition-colors ${expanded === c.id ? 'bg-[#f0f7f3]' : 'bg-white'}`}
              >
                <td className="px-5 py-4">
                  <button
                    onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                    className="flex items-center gap-2 font-semibold text-gray-800 hover:text-[#1a3a2a] transition-colors"
                  >
                    <span className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${expanded === c.id ? 'bg-[#1a3a2a] text-white' : 'bg-gray-100 text-gray-500'}`}>
                      {expanded === c.id
                        ? <ChevronUp className="w-3 h-3" />
                        : <ChevronDown className="w-3 h-3" />}
                    </span>
                    {c.CONSUMER_NAME}
                  </button>
                </td>
                <td className="px-5 py-4 text-gray-500 font-mono text-xs">{c.CONSUMER_APP_NO || '—'}</td>
                <td className="px-5 py-4 text-gray-600">{c.CONSUMER_PHONE}</td>

                <td className="px-5 py-4">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${DOC_STATUS_STYLES[c.doc_status] || DOC_STATUS_STYLES.none}`}>
                    {c.doc_status === 'generating' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {STATUS_LABELS[c.doc_status] || 'Not Generated'}
                  </span>
                </td>

                <td className="px-5 py-4">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${SIGN_STATUS_STYLES[c.signing_status] || SIGN_STATUS_STYLES.none}`}>
                    {STATUS_LABELS[c.signing_status] || 'Not Sent'}
                  </span>
                </td>

                <td className="px-5 py-4">
                  <div className="flex items-center justify-end gap-0.5">
                    <button
                      title="Generate Documents"
                      onClick={() => handleGenerateDocs(c)}
                      disabled={loadingId === `gen-${c.id}` || c.doc_status === 'generating'}
                      className="p-2 rounded-lg hover:bg-[#1a3a2a]/10 text-[#1a3a2a] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      {loadingId === `gen-${c.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                    </button>

                    <button
                      title="Send Signing Link"
                      onClick={() => handleSendLink(c)}
                      disabled={loadingId === `send-${c.id}` || c.doc_status !== 'complete'}
                      className="p-2 rounded-lg hover:bg-blue-50 text-blue-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      {loadingId === `send-${c.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>

                    <button
                      title="Download All Documents"
                      onClick={() => handleDownload(c)}
                      disabled={loadingId === `dl-${c.id}` || c.doc_status !== 'complete'}
                      className="p-2 rounded-lg hover:bg-emerald-50 text-emerald-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      {loadingId === `dl-${c.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    </button>

                    <div className="w-px h-4 bg-gray-200 mx-1" />

                    <button
                      title="Edit"
                      onClick={() => onEdit(c)}
                      className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700 transition-colors"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>

                    <button
                      title="Delete"
                      onClick={() => handleDelete(c)}
                      className="p-2 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>

              {expanded === c.id && (
                <tr key={`exp-${c.id}`} className="bg-[#f0f7f3]/70">
                  <td colSpan={6} className="px-5 py-4">
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                      {[
                        ['Email', c.CONSUMER_EMAIL],
                        ['Aadhar', c.CONSUMER_AADHAR],
                        ['Consumer No', c.CONSUMER_NO],
                        ['Solar Capacity', c.SOLAR_CAPACITY],
                        ['Inverter Make', c.INVERTER_MAKE],
                        ['Panel Company', c.PANEL_COMPANY],
                        ['No of Panels', c.NO_OF_PANEL],
                        ['Installation City', c.INSTALLATION_CITY],
                        ['Installation Date', c.INSTALLATION_DATE],
                        ['System Cost', c.SYSTEM_COST],
                        ['Meter Receipt No', c.METER_RECIPT_NO],
                        ['Generation Meter', c.GENERATION_METER_NO],
                      ].filter(([, val]) => val).map(([label, val]) => (
                        <div key={label} className="bg-white rounded-lg px-3 py-2 border border-[#1a3a2a]/10">
                          <p className="text-xs text-gray-400 mb-0.5">{label}</p>
                          <p className="text-sm font-medium text-gray-800">{val}</p>
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  )
}
