import { useState, useEffect, useRef } from 'react'
import { X, Check, Loader2, Calendar, User, Save, IndianRupee, Plus, Trash2 } from 'lucide-react'
import { getInstallation, updateInstallationStep, updateInstallationPayment } from '../api/installations'
import toast from 'react-hot-toast'

const fmtINR = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

// Map server received_payments → editable form rows.
const toRows = (entries) =>
  (entries || []).map((p) => ({
    amount: p.amount != null ? String(p.amount) : '',
    date: p.date || '',
  }))

// Stable serialization for dirty-checking (ignores empty rows).
const serializeRows = (rows) =>
  JSON.stringify(
    rows
      .filter((r) => r.amount !== '' && !Number.isNaN(parseFloat(r.amount)))
      .map((r) => ({ amount: parseFloat(r.amount) || 0, date: r.date || null }))
  )

export default function InstallationModal({ customer, onClose, onChanged }) {
  const [steps, setSteps] = useState([])      // server truth (with labels)
  const [edits, setEdits] = useState({})      // key -> { status, completed_date, performed_by, notes }
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState({})    // key -> bool
  const [pay, setPay] = useState({ total_payment: 0, received_payment: 0, remaining_payment: 0 })  // server truth
  const [payRows, setPayRows] = useState([])   // editable [{ amount: string, date: string }]
  const [savingPay, setSavingPay] = useState(false)
  const changedRef = useRef(false)
  const savedRowsRef = useRef('')              // serialized snapshot of last-saved rows

  async function load() {
    setLoading(true)
    try {
      const res = await getInstallation(customer.id)
      const data = res.data.data
      const s = data.steps
      setSteps(s)
      const e = {}
      s.forEach((step) => {
        e[step.key] = {
          status: step.status,
          completed_date: step.completed_date || '',
          performed_by: step.performed_by || '',
          notes: step.notes || '',
        }
      })
      setEdits(e)
      setPay({
        total_payment: data.total_payment || 0,
        received_payment: data.received_payment || 0,
        remaining_payment: data.remaining_payment || 0,
      })
      const rows = toRows(data.received_payments)
      setPayRows(rows)
      savedRowsRef.current = serializeRows(rows)
    } catch {
      toast.error('Failed to load installation steps')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer.id])

  function handleClose() {
    if (changedRef.current) onChanged?.()
    onClose()
  }

  function patch(key, field, value) {
    setEdits((prev) => ({ ...prev, [key]: { ...prev[key], [field]: value } }))
  }

  function toggleDone(key) {
    setEdits((prev) => {
      const cur = prev[key]
      const nextStatus = cur.status === 'done' ? 'pending' : 'done'
      return {
        ...prev,
        [key]: {
          ...cur,
          status: nextStatus,
          // Prefill today's date when marking done with no date yet.
          completed_date:
            nextStatus === 'done' && !cur.completed_date
              ? new Date().toISOString().slice(0, 10)
              : cur.completed_date,
        },
      }
    })
  }

  async function save(key) {
    const e = edits[key]
    setSaving((prev) => ({ ...prev, [key]: true }))
    try {
      const res = await updateInstallationStep(customer.id, key, {
        status: e.status,
        completed_date: e.completed_date || null,
        performed_by: e.performed_by || null,
        notes: e.notes || null,
      })
      changedRef.current = true
      const fresh = res.data.data.steps
      setSteps(fresh)
      // Re-sync this row from server (e.g. cleared fields when set back to pending).
      const updated = fresh.find((s) => s.key === key)
      if (updated) {
        setEdits((prev) => ({
          ...prev,
          [key]: {
            status: updated.status,
            completed_date: updated.completed_date || '',
            performed_by: updated.performed_by || '',
            notes: updated.notes || '',
          },
        }))
      }
      toast.success('Step updated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update step')
    } finally {
      setSaving((prev) => ({ ...prev, [key]: false }))
    }
  }

  function addPayRow() {
    setPayRows((rows) => [...rows, { amount: '', date: new Date().toISOString().slice(0, 10) }])
  }

  function updatePayRow(i, field, value) {
    setPayRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)))
  }

  function removePayRow(i) {
    setPayRows((rows) => rows.filter((_, idx) => idx !== i))
  }

  async function savePayment() {
    const entries = payRows
      .filter((r) => r.amount !== '' && !Number.isNaN(parseFloat(r.amount)))
      .map((r) => ({ amount: parseFloat(r.amount) || 0, date: r.date || null }))
    setSavingPay(true)
    try {
      const res = await updateInstallationPayment(customer.id, { received_payments: entries })
      changedRef.current = true
      const d = res.data.data
      setPay({
        total_payment: d.total_payment,
        received_payment: d.received_payment,
        remaining_payment: d.remaining_payment,
      })
      const rows = toRows(d.received_payments)
      setPayRows(rows)
      savedRowsRef.current = serializeRows(rows)
      toast.success('Payment updated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update payment')
    } finally {
      setSavingPay(false)
    }
  }

  const doneCount = steps.filter((s) => s.status === 'done').length
  const payDirty = serializeRows(payRows) !== savedRowsRef.current
  const liveReceived = payRows.reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0)
  const remaining = Math.max(pay.total_payment - liveReceived, 0)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={handleClose}>
      <div
        className="bg-white dark:bg-[#16201b] rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-gray-100 dark:border-white/10">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Installation Progress</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {customer.CONSUMER_NAME}
              {steps.length > 0 && (
                <span className="ml-2 text-gray-400 dark:text-gray-500">· {doneCount}/{steps.length} done</span>
              )}
            </p>
          </div>
          <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Payment */}
        {!loading && (
          <div className="px-6 pt-6">
            <div className="rounded-xl border border-gray-200 bg-gray-50/60 dark:border-white/10 dark:bg-white/5 p-4">
              <div className="flex items-center gap-2 mb-3">
                <IndianRupee className="w-4 h-4 text-[#1a3a2a] dark:text-emerald-400" />
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Payment</p>
              </div>
              {/* Total — read-only, sourced from the customer's System Cost */}
              <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] mb-3">
                <span className="text-xs text-gray-400 flex-shrink-0">Total (System Cost)</span>
                <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{fmtINR(pay.total_payment)}</span>
              </div>

              {/* Received — one dated entry per payment */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Received payments</span>
                <button
                  onClick={addPayRow}
                  className="inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold rounded-lg border border-[#1a3a2a]/30 text-[#1a3a2a] dark:border-emerald-500/30 dark:text-emerald-400 hover:bg-[#1a3a2a]/10 dark:hover:bg-emerald-500/10 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add
                </button>
              </div>

              {payRows.length === 0 ? (
                <p className="text-xs text-gray-400 dark:text-gray-500 italic">No payments recorded yet.</p>
              ) : (
                <div className="space-y-2">
                  {payRows.map((row, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] flex-1 min-w-0">
                        <span className="text-xs text-gray-400 flex-shrink-0">₹</span>
                        <input
                          type="number"
                          min="0"
                          placeholder="Amount"
                          value={row.amount}
                          onChange={(ev) => updatePayRow(i, 'amount', ev.target.value)}
                          className="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 focus:outline-none"
                        />
                      </label>
                      <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] flex-1 min-w-0">
                        <Calendar className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                        <input
                          type="date"
                          value={row.date}
                          onChange={(ev) => updatePayRow(i, 'date', ev.target.value)}
                          className="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 focus:outline-none"
                        />
                      </label>
                      <button
                        onClick={() => removePayRow(i)}
                        title="Remove payment"
                        className="p-2 rounded-lg text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 flex-shrink-0 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="text-xs font-medium">
                  <span className="text-gray-500 dark:text-gray-400">{fmtINR(liveReceived)} received</span>
                  {pay.total_payment > 0 && (
                    remaining > 0 ? (
                      <span className="text-amber-600 dark:text-amber-400"> · {fmtINR(remaining)} remaining</span>
                    ) : (
                      <span className="text-emerald-600 dark:text-emerald-400"> · Fully paid</span>
                    )
                  )}
                </span>
                {payDirty && (
                  <button
                    onClick={savePayment}
                    disabled={savingPay}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-50 transition-colors"
                  >
                    {savingPay ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    Save
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Steps */}
        <div className="p-6 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-gray-400">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
          ) : (
            steps.map((step) => {
              const e = edits[step.key] || {}
              const done = e.status === 'done'
              const isSaving = !!saving[step.key]
              const dirty =
                e.status !== step.status ||
                (e.completed_date || '') !== (step.completed_date || '') ||
                (e.performed_by || '') !== (step.performed_by || '') ||
                (e.notes || '') !== (step.notes || '')
              return (
                <div
                  key={step.key}
                  className={`rounded-xl border p-4 transition-colors ${done ? 'border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/20 dark:bg-emerald-500/10' : 'border-gray-200 bg-gray-50/60 dark:border-white/10 dark:bg-white/5'}`}
                >
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => toggleDone(step.key)}
                      title={done ? 'Mark as pending' : 'Mark as done'}
                      className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${done ? 'bg-emerald-500 text-white' : 'bg-gray-100 text-gray-400 hover:bg-gray-200 dark:bg-white/10 dark:text-gray-400 dark:hover:bg-white/20'}`}
                    >
                      <Check className="w-5 h-5" />
                    </button>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">{step.label}</p>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${done ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' : 'bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400'}`}>
                          {done ? 'Done' : 'Pending'}
                        </span>
                      </div>

                      {done && (
                        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b]">
                            <Calendar className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                            <input
                              type="date"
                              value={e.completed_date || ''}
                              onChange={(ev) => patch(step.key, 'completed_date', ev.target.value)}
                              className="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 focus:outline-none"
                            />
                          </label>
                          <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b]">
                            <User className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                            <input
                              type="text"
                              placeholder="Done by (name)"
                              value={e.performed_by || ''}
                              onChange={(ev) => patch(step.key, 'performed_by', ev.target.value)}
                              className="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 focus:outline-none"
                            />
                          </label>
                          <input
                            type="text"
                            placeholder="Notes (optional)"
                            value={e.notes || ''}
                            onChange={(ev) => patch(step.key, 'notes', ev.target.value)}
                            className="sm:col-span-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/30"
                          />
                        </div>
                      )}

                      {dirty && (
                        <div className="mt-3">
                          <button
                            onClick={() => save(step.key)}
                            disabled={isSaving}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-50 transition-colors"
                          >
                            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                            Save
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 dark:border-white/10 flex items-center justify-end">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm font-medium rounded-xl border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
