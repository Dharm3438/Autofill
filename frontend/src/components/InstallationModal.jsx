import { useState, useEffect, useRef } from 'react'
import { X, Check, Loader2, Calendar, User, Save, IndianRupee, Plus, Trash2, Hash, CalendarCheck } from 'lucide-react'
import { getInstallation, updateInstallationStep, updateInstallationGroup, updateInstallationPayment, updateInstallationSerials } from '../api/installations'
import toast from 'react-hot-toast'

import { fmtDate, fmtINR as fmtINRBlank } from '../utils/format'

const fmtINR = (n) => fmtINRBlank(n || 0)

// Amounts are whole rupees: "1500.6" → 1501.
const toRupees = (v) => Math.round(parseFloat(v)) || 0

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
      .map((r) => ({ amount: toRupees(r.amount), date: r.date || null }))
  )

// Shown alphabetically in the "Done by" list so names are easy to find.
const TEAM = [
  'Manoj Agone', 'Swapnil Jane', 'Vaibhav Gaikwad', 'Firoz Bhai', 'Yogesh Agone',
  'Pranav', 'Sidhesh', 'Kalpesh', 'Hussein', 'Aavesh', 'Anil Bachav',
  'Sonu Jadhav', 'Satish Khairnar', 'Kiran Chavan',
].sort((a, b) => a.localeCompare(b))

// The user's local calendar day. (toISOString() is UTC: in India it gave
// yesterday's date between midnight and 05:30.)
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Shorter chip labels inside a group ("ACDB Installation" → "ACDB").
const chipLabel = (label) => label.replace(/ Installation$/, '')

// Steps → render items: ungrouped steps stay single, consecutive steps sharing
// a `group` become one group item (they share a date and "done by").
function toItems(steps) {
  const items = []
  steps.forEach((step) => {
    if (!step.group) {
      items.push({ type: 'step', key: step.key, step })
      return
    }
    const last = items[items.length - 1]
    if (last?.type === 'group' && last.key === step.group) last.steps.push(step)
    else items.push({ type: 'group', key: step.group, label: step.group_label || step.group, steps: [step] })
  })
  return items
}

// A group's shared date / person, read from its first done member.
function groupShared(members) {
  const d = members.find((m) => m.status === 'done')
  return { completed_date: d?.completed_date || '', performed_by: d?.performed_by || '' }
}

function DoneDetails({ date, person, onDate, onPerson }) {
  return (
    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
      <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b]">
        <Calendar className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
        <input
          type="date"
          value={date || ''}
          onChange={(ev) => onDate(ev.target.value)}
          className="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 focus:outline-none"
        />
      </label>
      <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b]">
        <User className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
        <select
          value={person || ''}
          onChange={(ev) => onPerson(ev.target.value)}
          className="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 focus:outline-none cursor-pointer"
        >
          <option value="">Done by (select)</option>
          {TEAM.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
          {person && !TEAM.includes(person) && <option value={person}>{person}</option>}
        </select>
      </div>
    </div>
  )
}

function SaveButton({ onClick, saving }) {
  return (
    <div className="mt-3">
      <button
        onClick={onClick}
        disabled={saving}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-50 transition-colors"
      >
        {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
        Save
      </button>
    </div>
  )
}

export default function InstallationModal({ customer, onClose, onChanged }) {
  const [steps, setSteps] = useState([])      // server truth (with labels)
  const [edits, setEdits] = useState({})      // step key -> { status, completed_date, performed_by }
  const [groupEdits, setGroupEdits] = useState({})  // group key -> { completed_date, performed_by } (shared)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState({})    // key -> bool
  const [pay, setPay] = useState({ total_payment: 0, received_payment: 0, remaining_payment: 0 })  // server truth
  const [payRows, setPayRows] = useState([])   // editable [{ amount: string, date: string }]
  const [savingPay, setSavingPay] = useState(false)
  const [serials, setSerials] = useState({ INVERTER_SR_NO: '' })  // editable
  const [installationDate, setInstallationDate] = useState('')  // server-derived, read-only
  const [savingSerials, setSavingSerials] = useState(false)
  const changedRef = useRef(false)
  const savedRowsRef = useRef('')              // serialized snapshot of last-saved rows
  const savedSerialsRef = useRef('')           // JSON snapshot of last-saved serials

  async function load() {
    setLoading(true)
    try {
      const res = await getInstallation(customer.id)
      const data = res.data.data
      const s = data.steps
      syncSteps(s)
      setPay({
        total_payment: data.total_payment || 0,
        received_payment: data.received_payment || 0,
        remaining_payment: data.remaining_payment || 0,
      })
      const rows = toRows(data.received_payments)
      setPayRows(rows)
      savedRowsRef.current = serializeRows(rows)
      const sr = {
        INVERTER_SR_NO: data.INVERTER_SR_NO || '',
      }
      setSerials(sr)
      savedSerialsRef.current = JSON.stringify(sr)
      setInstallationDate(data.INSTALLATION_DATE || '')
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

  // Reset all checklist edit state from server steps.
  function syncSteps(s) {
    setSteps(s)
    const e = {}
    s.forEach((step) => {
      e[step.key] = {
        status: step.status,
        completed_date: step.completed_date || '',
        performed_by: step.performed_by || '',
      }
    })
    setEdits(e)
    const g = {}
    toItems(s).forEach((it) => {
      if (it.type === 'group') g[it.key] = groupShared(it.steps)
    })
    setGroupEdits(g)
  }

  function patchGroup(gkey, field, value) {
    setGroupEdits((prev) => ({ ...prev, [gkey]: { ...prev[gkey], [field]: value } }))
  }

  function toggleGroupMember(gkey, key) {
    const markingDone = edits[key]?.status !== 'done'
    setEdits((prev) => ({
      ...prev,
      [key]: { ...prev[key], status: markingDone ? 'done' : 'pending' },
    }))
    // Prefill today's date when the first member is ticked.
    if (markingDone && !groupEdits[gkey]?.completed_date) patchGroup(gkey, 'completed_date', today())
  }

  async function saveGroup(item) {
    const g = groupEdits[item.key] || {}
    setSaving((prev) => ({ ...prev, [item.key]: true }))
    try {
      const res = await updateInstallationGroup(customer.id, item.key, {
        done_keys: item.steps.filter((m) => edits[m.key]?.status === 'done').map((m) => m.key),
        completed_date: g.completed_date || null,
        performed_by: g.performed_by || null,
      })
      changedRef.current = true
      setInstallationDate(res.data.data.INSTALLATION_DATE || '')
      // Other cards may hold unsaved edits; keep them, refresh only this group.
      const fresh = res.data.data.steps
      setSteps(fresh)
      const members = fresh.filter((st) => st.group === item.key)
      setEdits((prev) => {
        const next = { ...prev }
        members.forEach((m) => {
          next[m.key] = { status: m.status, completed_date: m.completed_date || '', performed_by: m.performed_by || '' }
        })
        return next
      })
      setGroupEdits((prev) => ({ ...prev, [item.key]: groupShared(members) }))
      toast.success(`${item.label} updated`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update steps')
    } finally {
      setSaving((prev) => ({ ...prev, [item.key]: false }))
    }
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
            nextStatus === 'done' && !cur.completed_date ? today() : cur.completed_date,
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
      })
      changedRef.current = true
      const fresh = res.data.data.steps
      setSteps(fresh)
      // Marking the Inverter / Solar Panel Installation steps done (or clearing
      // their dates) re-derives the installation date server-side.
      setInstallationDate(res.data.data.INSTALLATION_DATE || '')
      // Re-sync this row from server (e.g. cleared fields when set back to pending).
      const updated = fresh.find((s) => s.key === key)
      if (updated) {
        setEdits((prev) => ({
          ...prev,
          [key]: {
            status: updated.status,
            completed_date: updated.completed_date || '',
            performed_by: updated.performed_by || '',
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
    setPayRows((rows) => [...rows, { amount: '', date: today() }])
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
      .map((r) => ({ amount: toRupees(r.amount), date: r.date || null }))
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

  function updateSerial(field, value) {
    setSerials((s) => ({ ...s, [field]: value }))
  }

  async function saveSerials() {
    setSavingSerials(true)
    try {
      const res = await updateInstallationSerials(customer.id, {
        INVERTER_SR_NO: serials.INVERTER_SR_NO.trim(),
      })
      changedRef.current = true
      const d = res.data.data
      const sr = {
        INVERTER_SR_NO: d.INVERTER_SR_NO || '',
      }
      setSerials(sr)
      savedSerialsRef.current = JSON.stringify(sr)
      toast.success('Serials saved')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save serial numbers')
    } finally {
      setSavingSerials(false)
    }
  }

  const doneCount = steps.filter((s) => s.status === 'done').length
  const serialsDirty = JSON.stringify(serials) !== savedSerialsRef.current
  const payDirty = serializeRows(payRows) !== savedRowsRef.current
  const liveReceived = payRows.reduce((sum, r) => sum + toRupees(r.amount), 0)
  const remaining = Math.max(pay.total_payment - liveReceived, 0)

  function renderStep(step) {
    const e = edits[step.key] || {}
    const done = e.status === 'done'
    const dirty =
      e.status !== step.status ||
      (e.completed_date || '') !== (step.completed_date || '') ||
      (e.performed_by || '') !== (step.performed_by || '')
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
              <DoneDetails
                date={e.completed_date}
                person={e.performed_by}
                onDate={(v) => patch(step.key, 'completed_date', v)}
                onPerson={(v) => patch(step.key, 'performed_by', v)}
              />
            )}

            {dirty && <SaveButton onClick={() => save(step.key)} saving={!!saving[step.key]} />}
          </div>
        </div>
      </div>
    )
  }

  function renderGroup(item) {
    const g = groupEdits[item.key] || {}
    const doneMembers = item.steps.filter((m) => edits[m.key]?.status === 'done')
    const allDone = doneMembers.length === item.steps.length
    const anyDone = doneMembers.length > 0
    const saved = groupShared(item.steps)
    const dirty =
      item.steps.some((m) => (edits[m.key]?.status || m.status) !== m.status) ||
      (anyDone &&
        ((g.completed_date || '') !== saved.completed_date ||
          (g.performed_by || '') !== saved.performed_by))
    return (
      <div
        key={`group-${item.key}`}
        className={`rounded-xl border p-4 transition-colors ${allDone ? 'border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/20 dark:bg-emerald-500/10' : 'border-gray-200 bg-gray-50/60 dark:border-white/10 dark:bg-white/5'}`}
      >
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">{item.label}</p>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${allDone ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' : anyDone ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300' : 'bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400'}`}>
            {allDone ? 'Done' : `${doneMembers.length}/${item.steps.length} done`}
          </span>
        </div>

        {/* One checkbox per step, laid out horizontally */}
        <div className="mt-3 flex flex-wrap gap-2">
          {item.steps.map((m) => {
            const done = edits[m.key]?.status === 'done'
            return (
              <button
                key={m.key}
                onClick={() => toggleGroupMember(item.key, m.key)}
                title={done ? 'Mark as pending' : 'Mark as done'}
                className={`inline-flex items-center gap-1.5 pl-1.5 pr-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors ${done ? 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-200' : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-100 dark:border-white/10 dark:bg-[#16201b] dark:text-gray-300 dark:hover:bg-white/10'}`}
              >
                <span className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 ${done ? 'bg-emerald-500 text-white' : 'border border-gray-300 dark:border-white/20'}`}>
                  {done && <Check className="w-3 h-3" />}
                </span>
                {chipLabel(m.label)}
              </button>
            )
          })}
        </div>

        {anyDone && (
          <DoneDetails
            date={g.completed_date}
            person={g.performed_by}
            onDate={(v) => patchGroup(item.key, 'completed_date', v)}
            onPerson={(v) => patchGroup(item.key, 'performed_by', v)}
          />
        )}

        {dirty && <SaveButton onClick={() => saveGroup(item)} saving={!!saving[item.key]} />}
      </div>
    )
  }

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
                          step="1"
                          inputMode="numeric"
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

        {/* Inverter serial number (recorded as data only) */}
        {!loading && (
          <div className="px-6 pt-6">
            <div className="rounded-xl border border-gray-200 bg-gray-50/60 dark:border-white/10 dark:bg-white/5 p-4">
              <div className="flex items-center gap-2 mb-1">
                <Hash className="w-4 h-4 text-[#1a3a2a] dark:text-emerald-400" />
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Inverter Serial Number</p>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Enter it once the inverter is installed. It can also be filled in on the
                customer form.
              </p>

              <div>
                <label className="block">
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Inverter Serial No</span>
                  <input
                    type="text"
                    value={serials.INVERTER_SR_NO}
                    onChange={(ev) => updateSerial('INVERTER_SR_NO', ev.target.value)}
                    placeholder="Inverter serial number"
                    className="mt-1 w-full px-2.5 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/30"
                  />
                </label>
              </div>

              {serialsDirty && (
                <div className="mt-3 flex items-center justify-end">
                  <button
                    onClick={saveSerials}
                    disabled={savingSerials}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-50 transition-colors flex-shrink-0"
                  >
                    {savingSerials ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    Save
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Steps */}
        <div className="p-6 space-y-3">
          {!loading && (
            <div className="flex items-center justify-between gap-2 pb-1">
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Installation Checklist</p>
              <span className="inline-flex items-center gap-1.5 text-xs">
                <CalendarCheck className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                {installationDate ? (
                  <span className="text-gray-600 dark:text-gray-300">
                    Installation date: <span className="font-semibold text-emerald-700 dark:text-emerald-300">{fmtDate(installationDate)}</span>
                  </span>
                ) : (
                  <span className="text-amber-600 dark:text-amber-400">
                    Not set — mark the Inverter or Solar Panel Installation step done
                  </span>
                )}
              </span>
            </div>
          )}
          {loading ? (
            <div className="flex items-center justify-center py-10 text-gray-400">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
          ) : (
            toItems(steps).map((item) =>
              item.type === 'group' ? renderGroup(item) : renderStep(item.step)
            )
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
