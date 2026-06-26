import { useState, useEffect, useCallback } from 'react'
import { Wrench, Search, RefreshCw, ChevronDown, ChevronRight, Settings2, Check } from 'lucide-react'
import { getInstallationOverview } from '../api/installations'
import InstallationStats from '../components/InstallationStats'
import InstallationModal from '../components/InstallationModal'
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

export default function InstallationsPage() {
  const [rows, setRows] = useState([])
  const [summary, setSummary] = useState(null)
  const [stepDefs, setStepDefs] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [pendingStep, setPendingStep] = useState('')
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
      })
      setRows(res.data.data)
      setSummary(res.data.summary)
      setStepDefs(res.data.steps)
    } catch {
      toast.error('Failed to load installation progress')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, pendingStep])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  function toggleRow(id) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
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
              {rows.map((c) => {
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
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[c.overall_status]}`}>
                            {STATUS_LABEL[c.overall_status]}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {[c.INSTALLATION_CITY, c.CONSUMER_PHONE].filter(Boolean).join(' · ') || '—'}
                        </p>
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

                    {/* Expanded step chips */}
                    {open && (
                      <div className="mt-4 pl-9 flex flex-wrap gap-2">
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
