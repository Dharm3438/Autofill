import { useState, useEffect, useCallback, useMemo } from 'react'
import { Wrench, Search, RefreshCw, ChevronDown, ChevronRight, Settings2, Check, Printer } from 'lucide-react'
import { getInstallationOverview } from '../api/installations'
import { DEALER_OPTIONS } from '../constants/dealers'
import InstallationStats from '../components/InstallationStats'
import InstallationModal from '../components/InstallationModal'
import { printInstallations } from '../utils/printInstallations'
import toast from 'react-hot-toast'

const STATUS_BADGE = {
  completed: 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20',
  in_progress: 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20',
  not_started: 'bg-gray-100 text-gray-500 border border-gray-200 dark:bg-white/5 dark:text-gray-400 dark:border-white/10',
}
const STATUS_LABEL = {
  completed: 'Completed',
  in_progress: 'In Progress',
  not_started: 'Not Started',
}

// ₹ with Indian thousands grouping, no decimals (e.g. ₹50,000).
const fmtINR = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

// Order the status circles are shown in below each customer's name.
// Independent of the checklist order — this is purely the at-a-glance row.
const CIRCLE_ORDER = [
  'structure', 'painting', 'cement_grouting', 'wiring', 'earthing_la',
  'acdb', 'dcdb', 'inverter', 'panels', 'generation_meter',
  'net_meter', 'document_upload', 'dcr_ready', 'subsidy_received',
]

// Return a customer's steps ordered for the circle row. Any step not listed in
// CIRCLE_ORDER (e.g. a future addition) is appended at the end so nothing is lost.
function orderedCircleSteps(steps) {
  const byKey = new Map((steps || []).map((s) => [s.key, s]))
  const ordered = CIRCLE_ORDER.map((k) => byKey.get(k)).filter(Boolean)
  const extras = (steps || []).filter((s) => !CIRCLE_ORDER.includes(s.key))
  return [...ordered, ...extras]
}

export default function InstallationsPage() {
  const [rows, setRows] = useState([])
  const [summary, setSummary] = useState(null)
  const [stepDefs, setStepDefs] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [pendingStep, setPendingStep] = useState('')
  const [dealerFilter, setDealerFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState({})
  const [manageCustomer, setManageCustomer] = useState(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getInstallationOverview({
        search,
        status: statusFilter,
        pending_step: pendingStep,
        dealer: dealerFilter,
      })
      setRows(res.data.data)
      setSummary(res.data.summary)
      setStepDefs(res.data.steps)
    } catch {
      toast.error('Failed to load installation progress')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, pendingStep, dealerFilter])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // The list exactly as rendered below — sorted by completion %, then name.
  // Shared by the on-screen list and the print sheet so they stay in sync.
  const sortedRows = useMemo(
    () =>
      [...rows].sort((a, b) => {
        const pctA = a.total ? a.done_count / a.total : 0
        const pctB = b.total ? b.done_count / b.total : 0
        if (pctB !== pctA) return pctB - pctA
        return (a.CONSUMER_NAME || '').localeCompare(b.CONSUMER_NAME || '', undefined, { sensitivity: 'base' })
      }),
    [rows],
  )

  function toggleRow(id) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  function handlePrint() {
    if (sortedRows.length === 0) {
      toast.error('Nothing to print — no customers match the current filters')
      return
    }
    const pendingLabel = pendingStep
      ? stepDefs.find((s) => s.key === pendingStep)?.label || pendingStep
      : ''
    const ok = printInstallations(sortedRows, {
      filters: [
        { label: 'Search', value: search },
        { label: 'Dealer', value: dealerFilter },
        { label: 'Status', value: STATUS_LABEL[statusFilter] || '' },
        { label: 'Pending step', value: pendingLabel },
      ],
    })
    if (!ok) toast.error('Allow pop-ups to print the report')
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <div className="w-11 h-11 rounded-xl bg-[#1a3a2a] flex items-center justify-center shadow-sm">
            <Wrench className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Installation Progress</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              Track what's done and what's remaining for each customer
            </p>
          </div>
        </div>

        {/* Summary stats */}
        <div className="mb-6">
          <InstallationStats summary={summary} />
        </div>

        {/* Filter bar */}
        <div className="flex flex-col sm:flex-row gap-3 mb-5">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
            <input
              type="text"
              placeholder="Search by name or phone…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 transition-all shadow-sm"
            />
          </div>
          <select
            value={dealerFilter}
            onChange={(e) => setDealerFilter(e.target.value)}
            className="px-3 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 shadow-sm"
          >
            <option value="">All dealers</option>
            {DEALER_OPTIONS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 shadow-sm"
          >
            <option value="">All statuses</option>
            <option value="not_started">Not Started</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
          </select>
          <select
            value={pendingStep}
            onChange={(e) => setPendingStep(e.target.value)}
            className="px-3 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 shadow-sm"
          >
            <option value="">Any pending step</option>
            {stepDefs.map((s) => (
              <option key={s.key} value={s.key}>Pending: {s.label}</option>
            ))}
          </select>
          <button
            onClick={handlePrint}
            disabled={loading || rows.length === 0}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            title="Print the list shown below (filters applied)"
          >
            <Printer className="w-4 h-4" />
            <span className="hidden sm:inline">Print</span>
          </button>
        </div>

        {/* List */}
        <div className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden shadow-sm">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 gap-3">
              <RefreshCw className="w-6 h-6 text-[#1a3a2a] dark:text-emerald-400 animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
            </div>
          ) : rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-14 h-14 rounded-2xl bg-gray-100 dark:bg-white/5 flex items-center justify-center mb-4">
                <Wrench className="w-6 h-6 text-gray-400 dark:text-gray-500" />
              </div>
              <p className="text-gray-600 dark:text-gray-300 font-medium mb-1">No customers found</p>
              <p className="text-sm text-gray-400 dark:text-gray-500">Try adjusting the filters</p>
            </div>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-white/10">
              {sortedRows.map((c) => {
                const pct = c.total ? Math.round((c.done_count / c.total) * 100) : 0
                const open = !!expanded[c.id]
                return (
                  <li key={c.id} className="px-4 sm:px-6 py-4">
                    <div className="flex items-center gap-4">
                      <button
                        onClick={() => toggleRow(c.id)}
                        className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 text-gray-400 flex-shrink-0"
                        aria-label={open ? 'Collapse' : 'Expand'}
                      >
                        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </button>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                            {c.CONSUMER_NAME || 'Unnamed'}
                          </p>
                          {c.received_payment > 0 && (
                            <span
                              title="Payment received"
                              className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20"
                            >
                              +{fmtINR(c.received_payment)}
                            </span>
                          )}
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[c.overall_status]}`}>
                            {STATUS_LABEL[c.overall_status]}
                          </span>
                        </div>
                        <div className="mt-0.5 space-y-0.5 text-xs text-gray-500 dark:text-gray-400">
                          {c.DEALER_NAME && (
                            <p>Dealer: <span className="text-gray-600 dark:text-gray-300">{c.DEALER_NAME}</span></p>
                          )}
                          <p>{[c.CONSUMER_NO, c.INSTALLATION_CITY, c.CONSUMER_PHONE].filter(Boolean).join(' · ') || '—'}</p>
                          {[c.INVERTER_MAKE, c.INVERTER_CAPACITY].filter(Boolean).length > 0 && (
                            <p>{[c.INVERTER_MAKE, c.INVERTER_CAPACITY].filter(Boolean).join(' · ')}</p>
                          )}
                          {[c.PANEL_COMPANY, c.PANEL_WATT, c.NO_OF_PANEL].filter(Boolean).length > 0 && (
                            <p>{[c.PANEL_COMPANY, c.PANEL_WATT, c.NO_OF_PANEL].filter(Boolean).join(' · ')}</p>
                          )}
                        </div>

                        {/* At-a-glance status circles — red = pending, green = done */}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {orderedCircleSteps(c.steps).map((s) => {
                            const done = s.status === 'done'
                            const tip = done
                              ? `${s.label} — Done${[s.completed_date, s.performed_by].filter(Boolean).length ? ' (' + [s.completed_date, s.performed_by].filter(Boolean).join(' · ') + ')' : ''}`
                              : `${s.label} — Pending`
                            return (
                              <span
                                key={s.key}
                                title={tip}
                                className={`inline-flex items-center justify-center min-w-[1.4rem] h-5 px-1 rounded-full text-[10px] font-bold leading-none cursor-default select-none transition-colors ${
                                  done
                                    ? 'bg-emerald-500 text-white'
                                    : 'bg-red-500 text-white'
                                }`}
                              >
                                {s.short || s.label?.slice(0, 2)}
                              </span>
                            )
                          })}
                        </div>
                      </div>

                      {/* Progress */}
                      <div className="hidden sm:flex items-center gap-3 w-44 flex-shrink-0">
                        <div className="flex-1 h-2 rounded-full bg-gray-100 dark:bg-white/10 overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 w-9 text-right">
                          {c.done_count}/{c.total}
                        </span>
                      </div>

                      <button
                        onClick={() => setManageCustomer(c)}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] transition-colors flex-shrink-0"
                      >
                        <Settings2 className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Manage</span>
                      </button>
                    </div>

                    {/* Mobile progress */}
                    <div className="sm:hidden flex items-center gap-3 mt-3">
                      <div className="flex-1 h-2 rounded-full bg-gray-100 dark:bg-white/10 overflow-hidden">
                        <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{c.done_count}/{c.total}</span>
                    </div>

                    {/* Expanded: payment summary + step chips */}
                    {open && (
                      <div className="mt-4 pl-9">
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-3 text-xs">
                          <span className="text-gray-500 dark:text-gray-400">
                            Total: <span className="font-medium text-gray-700 dark:text-gray-200">{fmtINR(c.total_payment)}</span>
                          </span>
                          <span className="text-gray-500 dark:text-gray-400">
                            Received: <span className="font-medium text-emerald-700 dark:text-emerald-300">{fmtINR(c.received_payment)}</span>
                          </span>
                          {c.remaining_payment > 0 ? (
                            <span className="font-medium text-amber-600 dark:text-amber-400">
                              {fmtINR(c.remaining_payment)} remaining
                            </span>
                          ) : (
                            <span className="font-medium text-emerald-600 dark:text-emerald-400">Fully paid</span>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {c.steps.map((s) => {
                          const done = s.status === 'done'
                          return (
                            <div
                              key={s.key}
                              title={done && (s.performed_by || s.completed_date)
                                ? `${s.completed_date || ''}${s.performed_by ? ' · ' + s.performed_by : ''}${s.notes ? ' · ' + s.notes : ''}`
                                : undefined}
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs ${done ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300' : 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400'}`}
                            >
                              {done && <Check className="w-3 h-3" />}
                              {s.label}
                              {done && (s.completed_date || s.performed_by) && (
                                <span className="text-emerald-600/70 dark:text-emerald-400/70">
                                  · {[s.completed_date, s.performed_by].filter(Boolean).join(' · ')}
                                </span>
                              )}
                            </div>
                          )
                        })}
                        </div>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      {manageCustomer && (
        <InstallationModal
          customer={manageCustomer}
          onClose={() => setManageCustomer(null)}
          onChanged={fetchData}
        />
      )}
    </div>
  )
}
