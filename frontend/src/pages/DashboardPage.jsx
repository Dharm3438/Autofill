import { useNavigate } from 'react-router-dom'
import { Users, UserPlus, FileText, Sun } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()

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
      </div>
    </div>
  )
}
