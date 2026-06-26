import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, UserPlus, FileText, Sun, Wrench, ArrowRight } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getInstallationOverview } from '../api/installations'
import InstallationStats from '../components/InstallationStats'

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [summary, setSummary] = useState(null)
  const [steps, setSteps] = useState([])

  useEffect(() => {
    getInstallationOverview()
      .then((res) => {
        setSummary(res.data.summary)
        setSteps(res.data.steps)
      })
      .catch(() => {})
  }, [])

  // Most-pending steps first, drop the ones nobody is waiting on.
  const topRemaining = steps
    .map((s) => ({ ...s, count: summary?.per_step_pending?.[s.key] ?? 0 }))
    .filter((s) => s.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512]">
      {/* Hero Banner */}
      <div className="bg-[#1a3a2a] dark:bg-[#13241b] dark:border-b dark:border-white/5 px-4 sm:px-6 lg:px-8 py-8 sm:py-10">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            <Sun className="w-6 h-6 text-white/60" />
            <span className="text-white/60 text-sm font-medium">Solar Document Platform</span>
          </div>
          <h1 className="text-2xl font-bold text-white">
            Welcome back, {user?.name || 'Admin'}
          </h1>
          <p className="text-white/60 text-sm mt-1">
            Manage solar installation customers and auto-generate regulatory documents.
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-4">Quick Actions</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-4 bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 p-6 hover:border-[#1a3a2a] dark:hover:border-emerald-500/50 hover:shadow-md dark:hover:shadow-black/30 transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 dark:bg-emerald-500/15 flex items-center justify-center group-hover:bg-[#1a3a2a] dark:group-hover:bg-emerald-500 transition-colors flex-shrink-0">
              <UserPlus className="w-5 h-5 text-[#1a3a2a] dark:text-emerald-400 group-hover:text-white dark:group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-1 group-hover:text-[#1a3a2a] dark:group-hover:text-emerald-400 transition-colors">Add Customer</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">Enter new solar installation customer details and generate their documents.</p>
            </div>
          </button>

          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-4 bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 p-6 hover:border-[#1a3a2a] dark:hover:border-emerald-500/50 hover:shadow-md dark:hover:shadow-black/30 transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 dark:bg-emerald-500/15 flex items-center justify-center group-hover:bg-[#1a3a2a] dark:group-hover:bg-emerald-500 transition-colors flex-shrink-0">
              <Users className="w-5 h-5 text-[#1a3a2a] dark:text-emerald-400 group-hover:text-white dark:group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-1 group-hover:text-[#1a3a2a] dark:group-hover:text-emerald-400 transition-colors">View All Customers</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">Browse customers, generate docs, and send signing links via email.</p>
            </div>
          </button>

          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-4 bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 p-6 hover:border-[#1a3a2a] dark:hover:border-emerald-500/50 hover:shadow-md dark:hover:shadow-black/30 transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 dark:bg-emerald-500/15 flex items-center justify-center group-hover:bg-[#1a3a2a] dark:group-hover:bg-emerald-500 transition-colors flex-shrink-0">
              <FileText className="w-5 h-5 text-[#1a3a2a] dark:text-emerald-400 group-hover:text-white dark:group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-1 group-hover:text-[#1a3a2a] dark:group-hover:text-emerald-400 transition-colors">Generate Documents</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">Auto-generate Annexure, WCR, DCR, and all required regulatory documents.</p>
            </div>
          </button>
        </div>

        {/* Installation Progress overview */}
        <div className="mt-10">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">Installation Progress</p>
            <button
              onClick={() => navigate('/installations')}
              className="inline-flex items-center gap-1 text-sm font-medium text-[#1a3a2a] dark:text-emerald-400 hover:underline"
            >
              View all
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          <InstallationStats summary={summary} />

          {topRemaining.length > 0 && (
            <div className="mt-4 bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <Wrench className="w-4 h-4 text-[#1a3a2a] dark:text-emerald-400" />
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Top remaining steps</p>
              </div>
              <ul className="space-y-2">
                {topRemaining.map((s) => (
                  <li key={s.key}>
                    <button
                      onClick={() => navigate('/installations')}
                      className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-white/5 transition-colors text-left"
                    >
                      <span className="text-sm text-gray-700 dark:text-gray-200">{s.label}</span>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
                        {s.count} pending
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
