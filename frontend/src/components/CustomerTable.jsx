import { useState, useEffect, useRef } from 'react'
import { Pencil, Trash2, FileText, Send, Download, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { deleteCustomer } from '../api/customers'
import { generateDocs, getDocStatus, sendSigningLink, downloadZip } from '../api/documents'
import toast from 'react-hot-toast'

const STATUS_COLORS = {
  none:       'bg-gray-100 text-gray-500',
  generating: 'bg-yellow-100 text-yellow-700',
  complete:   'bg-green-100 text-green-700',
  failed:     'bg-red-100 text-red-600',
  sent:       'bg-blue-100 text-blue-700',
  signed:     'bg-green-100 text-green-700',
}

const STATUS_LABELS = {
  none:       'Not generated',
  generating: 'Generating…',
  complete:   'Complete',
  failed:     'Failed',
  sent:       'Sent',
  signed:     'Signed',
}

export default function CustomerTable({ customers, onEdit, onRefresh }) {
  const [expanded, setExpanded]   = useState(null)
  const [loadingId, setLoadingId] = useState(null)
  // Track which customers are currently generating so we can poll
  const pollingRef = useRef({})

  // Poll status for any customer currently in "generating" state
  useEffect(() => {
    const generating = customers.filter(c => c.doc_status === 'generating')
    generating.forEach(c => {
      if (pollingRef.current[c.id]) return   // already polling
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
      // Clean up intervals for customers no longer generating
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
          <tr className="border-b border-[#eeecea] bg-[#f7f7f5]">
            <th className="text-left px-5 py-3 font-medium text-[#5a5f72]">Name</th>
            <th className="text-left px-5 py-3 font-medium text-[#5a5f72]">App No</th>
            <th className="text-left px-5 py-3 font-medium text-[#5a5f72]">Phone</th>
            <th className="text-left px-5 py-3 font-medium text-[#5a5f72]">Docs</th>
            <th className="text-left px-5 py-3 font-medium text-[#5a5f72]">Signing</th>
            <th className="text-right px-5 py-3 font-medium text-[#5a5f72]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <>
              <tr key={c.id} className="border-b border-[#eeecea] hover:bg-[#f7f7f5] transition-colors">
                <td className="px-5 py-3.5 font-medium text-[#0f1117]">
                  <button
                    onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                    className="flex items-center gap-1.5 hover:text-[#1a3a2a]"
                  >
                    {expanded === c.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    {c.CONSUMER_NAME}
                  </button>
                </td>
                <td className="px-5 py-3.5 text-[#5a5f72]">{c.CONSUMER_APP_NO || '—'}</td>
                <td className="px-5 py-3.5 text-[#5a5f72]">{c.CONSUMER_PHONE}</td>

                <td className="px-5 py-3.5">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[c.doc_status] || STATUS_COLORS.none}`}>
                    {c.doc_status === 'generating' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {STATUS_LABELS[c.doc_status] || 'Not generated'}
                  </span>
                </td>

                <td className="px-5 py-3.5">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[c.signing_status] || STATUS_COLORS.none}`}>
                    {STATUS_LABELS[c.signing_status] || 'Not sent'}
                  </span>
                </td>

                <td className="px-5 py-3.5">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      title="Generate Documents"
                      onClick={() => handleGenerateDocs(c)}
                      disabled={loadingId === `gen-${c.id}` || c.doc_status === 'generating'}
                      className="p-1.5 rounded-lg hover:bg-[#1a3a2a]/10 text-[#1a3a2a] disabled:opacity-40 transition-colors"
                    >
                      {loadingId === `gen-${c.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                    </button>

                    <button
                      title="Send Signing Link"
                      onClick={() => handleSendLink(c)}
                      disabled={loadingId === `send-${c.id}` || c.doc_status !== 'complete'}
                      className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-600 disabled:opacity-40 transition-colors"
                    >
                      {loadingId === `send-${c.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>

                    <button
                      title="Download All Documents"
                      onClick={() => handleDownload(c)}
                      disabled={loadingId === `dl-${c.id}` || c.doc_status !== 'complete'}
                      className="p-1.5 rounded-lg hover:bg-green-50 text-green-700 disabled:opacity-40 transition-colors"
                    >
                      {loadingId === `dl-${c.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    </button>

                    <button
                      title="Edit"
                      onClick={() => onEdit(c)}
                      className="p-1.5 rounded-lg hover:bg-gray-100 text-[#5a5f72] transition-colors"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>

                    <button
                      title="Delete"
                      onClick={() => handleDelete(c)}
                      className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>

              {expanded === c.id && (
                <tr key={`exp-${c.id}`} className="bg-[#f7f7f5] border-b border-[#eeecea]">
                  <td colSpan={6} className="px-5 py-4">
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-8 gap-y-2 text-xs">
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
                      ].map(([label, val]) => val ? (
                        <div key={label}>
                          <span className="text-[#9399aa]">{label}: </span>
                          <span className="text-[#0f1117] font-medium">{val}</span>
                        </div>
                      ) : null)}
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
