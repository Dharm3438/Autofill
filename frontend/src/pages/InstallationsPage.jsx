import { useState, useEffect, useCallback, useRef } from 'react'
import { Wrench, Search, RefreshCw, Settings2, Printer } from 'lucide-react'
import { getInstallationOverview } from '../api/installations'
import { DEALER_OPTIONS } from '../constants/dealers'
import InstallationStats from '../components/InstallationStats'
import InstallationModal from '../components/InstallationModal'
import InventorySidebar from '../components/InventorySidebar'
import { printInstallations, openPrintWindow } from '../utils/printInstallations'
import toast from 'react-hot-toast'

// Rows per page — same as the Customers page.
const PAGE_SIZE = 20

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

// Panel watt and count are stored as bare numbers ("540", "10"); add units so
// the line reads naturally ("540 W", "10 panels"). Text values pass through as-is.
function panelWatt(w) {
  if (w == null || w === '') return ''
  const str = String(w).trim()
  return /^\d+(\.\d+)?$/.test(str) ? `${str} W` : str
}

function panelCount(n) {
  if (n == null || n === '') return ''
  const str = String(n).trim()
  if (!/^\d+$/.test(str)) return str
  return `${str} ${str === '1' ? 'panel' : 'panels'}`
}

// One line: "Inverter: Growatt · 5 kW | Panels: Waaree · 540 W · 10 panels".
// A side with no data is left out; the whole line is hidden if both are empty.
function EquipmentLine({ customer: c }) {
  const inverter = [c.INVERTER_MAKE, c.INVERTER_CAPACITY].filter(Boolean).join(' · ')
  const panels = [c.PANEL_COMPANY, panelWatt(c.PANEL_WATT), panelCount(c.NO_OF_PANEL)].filter(Boolean).join(' · ')
  if (!inverter && !panels) return null
  return (
    <p className="flex flex-wrap items-center gap-x-2">
      {inverter && (
        <span>Inverter: <span className="text-gray-600 dark:text-gray-300">{inverter}</span></span>
      )}
      {inverter && panels && <span aria-hidden="true" className="text-gray-300 dark:text-gray-600">|</span>}
      {panels && (
        <span>Panels: <span className="text-gray-600 dark:text-gray-300">{panels}</span></span>
      )}
    </p>
  )
}

// "Payment: ₹20,000 of ₹1,00,000 · ₹80,000 remaining" (or "Fully paid").
// Without a system cost there's no total to compare against, so only the
// received amount is shown with a hint that the total is missing.
function PaymentLine({ customer: c }) {
  const received = c.received_payment || 0
  const total = c.total_payment || 0
  return (
    <p>
      Payment:{' '}
      <span className="font-medium text-gray-700 dark:text-gray-200">{fmtINR(received)}</span>
      {total > 0 ? (
        <>
          {' '}of <span className="font-medium text-gray-700 dark:text-gray-200">{fmtINR(total)}</span>
          {' · '}
          {c.remaining_payment > 0 ? (
            <span className="font-medium text-amber-600 dark:text-amber-400">{fmtINR(c.remaining_payment)} remaining</span>
          ) : (
            <span className="font-medium text-emerald-600 dark:text-emerald-400">Fully paid</span>
          )}
        </>
      ) : (
        <> received · <span className="italic">total not set</span></>
      )}
    </p>
  )
}

export default function InstallationsPage() {
  const [rows, setRows] = useState([])
  // Rows matching every filter (all pages) — drives the pager.
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [printing, setPrinting] = useState(false)
  const [summary, setSummary] = useState(null)
  const [stepDefs, setStepDefs] = useState([])
  const [search, setSearch] = useState('')
  // Debounced copy of `search` so a full-scan overview isn't re-run on every
  // keystroke — only once typing settles. Other filters are dropdowns (one
  // change at a time), so they fetch immediately.
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [pendingStep, setPendingStep] = useState('')
  const [dealerFilter, setDealerFilter] = useState('')
  // True from the start so the first paint shows the spinner, not the empty state.
  const [loading, setLoading] = useState(true)
  const [manageCustomer, setManageCustomer] = useState(null)
  // Bumped whenever an installation change is saved, so the inventory sidebar
  // refetches (a completed step moves a unit from "required" to "in stock used").
  const [inventoryRefresh, setInventoryRefresh] = useState(0)

  useEffect(() => {
    if (search === debouncedSearch) return
    // A new search shows its first page.
    const t = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 350)
    return () => clearTimeout(t)
  }, [search, debouncedSearch])

  // The filters as API params — shared by the page fetch and Print.
  const filterParams = useCallback(() => ({
    search: debouncedSearch,
    status: statusFilter,
    pending_step: pendingStep,
    dealer: dealerFilter,
  }), [debouncedSearch, statusFilter, pendingStep, dealerFilter])

  // Only the newest request may update the list (an older, slower response
  // must not overwrite it).
  const requestIdRef = useRef(0)

  const fetchData = useCallback(async () => {
    const id = ++requestIdRef.current
    setLoading(true)
    try {
      const res = await getInstallationOverview({ ...filterParams(), page, limit: PAGE_SIZE })
      if (id !== requestIdRef.current) return
      const { data, total: count, summary: sum, steps } = res.data
      // The current page can empty out (e.g. after Manage moves a customer to
      // another status under an active filter) — step back to the last page.
      const lastPage = Math.max(1, Math.ceil(count / PAGE_SIZE))
      if (page > lastPage) {
        setPage(lastPage)
        return
      }
      setRows(data)
      setTotal(count)
      setSummary(sum)
      setStepDefs(steps)
    } catch {
      if (id === requestIdRef.current) toast.error('Failed to load installation progress')
    } finally {
      if (id === requestIdRef.current) setLoading(false)
    }
  }, [filterParams, page])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  // A filter change shows its first page.
  function changeFilter(setter) {
    return (e) => {
      setter(e.target.value)
      setPage(1)
    }
  }

  // Print covers every customer matching the filters, not just this page, so
  // fetch them all (already sorted by the server) only when Print is clicked.
  async function handlePrint() {
    if (total === 0) {
      toast.error('Nothing to print — no customers match the current filters')
      return
    }
    const win = openPrintWindow()
    if (!win) {
      toast.error('Allow pop-ups to print the report')
      return
    }
    setPrinting(true)
    try {
      const res = await getInstallationOverview({ ...filterParams(), all: true })
      const pendingLabel = pendingStep
        ? stepDefs.find((s) => s.key === pendingStep)?.label || pendingStep
        : ''
      const ok = printInstallations(res.data.data, {
        win,
        filters: [
          { label: 'Search', value: debouncedSearch },
          { label: 'Dealer', value: dealerFilter },
          { label: 'Status', value: STATUS_LABEL[statusFilter] || '' },
          { label: 'Pending step', value: pendingLabel },
        ],
      })
      if (!ok) toast.error('The print window was closed')
    } catch {
      win.close()
      toast.error('Failed to load customers for printing')
    } finally {
      setPrinting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512]">
      <div className="max-w-[88rem] mx-auto px-4 sm:px-6 lg:px-8 py-8">

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

        {/* Two-column: list (left) + inventory sidebar (right on desktop, below on mobile) */}
        <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex-1 min-w-0">

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
            onChange={changeFilter(setDealerFilter)}
            className="px-3 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 shadow-sm"
          >
            <option value="">All dealers</option>
            {DEALER_OPTIONS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={changeFilter(setStatusFilter)}
            className="px-3 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 shadow-sm"
          >
            <option value="">All statuses</option>
            <option value="not_started">Not Started</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
          </select>
          <select
            value={pendingStep}
            onChange={changeFilter(setPendingStep)}
            className="px-3 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 shadow-sm"
          >
            <option value="">Any pending step</option>
            {stepDefs.map((s) => (
              <option key={s.key} value={s.key}>Pending: {s.label}</option>
            ))}
          </select>
          <button
            onClick={handlePrint}
            disabled={loading || printing || total === 0}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            title="Print the list shown below (filters applied)"
          >
            {printing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Printer className="w-4 h-4" />}
            <span className="hidden sm:inline">Print</span>
          </button>
        </div>

        {/* List */}
        <div className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden shadow-sm">
          {/* Full spinner only when there's nothing on screen yet; a background
              refetch (e.g. after a Manage save) keeps the rows visible, dimmed,
              so the scroll position survives it. */}
          {loading && rows.length === 0 ? (
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
            <ul className={`divide-y divide-gray-100 dark:divide-white/10 transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
              {rows.map((c) => {
                const pct = c.total ? Math.round((c.done_count / c.total) * 100) : 0
                return (
                  <li key={c.id} className="px-4 sm:px-6 py-4">
                    <div className="flex items-center gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                            {c.CONSUMER_NAME || 'Unnamed'}
                          </p>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[c.overall_status]}`}>
                            {STATUS_LABEL[c.overall_status]}
                          </span>
                        </div>
                        <div className="mt-0.5 space-y-0.5 text-xs text-gray-500 dark:text-gray-400">
                          {c.DEALER_NAME && (
                            <p>Dealer: <span className="text-gray-600 dark:text-gray-300">{c.DEALER_NAME}</span></p>
                          )}
                          <p>{[c.CONSUMER_NO, c.INSTALLATION_CITY, c.CONSUMER_PHONE].filter(Boolean).join(' · ') || '—'}</p>
                          <EquipmentLine customer={c} />
                          <PaymentLine customer={c} />
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
                                    ? 'bg-emerald-100 text-emerald-700 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
                                    : 'bg-red-100 text-red-600 border border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'
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

                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Pagination — same as the Customers page */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Page <span className="font-medium text-gray-700 dark:text-gray-200">{page}</span> of{' '}
              <span className="font-medium text-gray-700 dark:text-gray-200">{totalPages}</span>
            </p>
            <div className="flex gap-2">
              <button
                disabled={page === 1 || loading}
                onClick={() => setPage(p => p - 1)}
                className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-white/10 rounded-xl bg-white dark:bg-[#16201b] text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:border-[#1a3a2a] hover:text-[#1a3a2a] dark:hover:border-emerald-500/50 dark:hover:text-emerald-400 transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page === totalPages || loading}
                onClick={() => setPage(p => p + 1)}
                className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-white/10 rounded-xl bg-white dark:bg-[#16201b] text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:border-[#1a3a2a] hover:text-[#1a3a2a] dark:hover:border-emerald-500/50 dark:hover:text-emerald-400 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}

        </div>{/* /list column */}

        {/* Inventory sidebar — sticky on desktop, stacked below on mobile */}
        <aside className="lg:w-80 xl:w-96 flex-shrink-0">
          <div className="lg:sticky lg:top-8">
            <InventorySidebar refreshSignal={inventoryRefresh} />
          </div>
        </aside>
        </div>{/* /two-column */}
      </div>

      {manageCustomer && (
        <InstallationModal
          customer={manageCustomer}
          onClose={() => setManageCustomer(null)}
          onChanged={() => { fetchData(); setInventoryRefresh((n) => n + 1) }}
        />
      )}
    </div>
  )
}
