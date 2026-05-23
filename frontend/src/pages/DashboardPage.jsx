import { useNavigate } from 'react-router-dom'
import { Users, UserPlus, FileText, Sun } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Hero Banner */}
      <div className="bg-[#1a3a2a] px-8 py-10">
        <div className="max-w-4xl mx-auto">
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

      <div className="max-w-4xl mx-auto px-8 py-8">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Quick Actions</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-4 bg-white rounded-2xl border border-gray-200 p-6 hover:border-[#1a3a2a] hover:shadow-md transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 flex items-center justify-center group-hover:bg-[#1a3a2a] transition-colors flex-shrink-0">
              <UserPlus className="w-5 h-5 text-[#1a3a2a] group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900 mb-1 group-hover:text-[#1a3a2a] transition-colors">Add Customer</h2>
              <p className="text-sm text-gray-500 leading-relaxed">Enter new solar installation customer details and generate their documents.</p>
            </div>
          </button>

          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-4 bg-white rounded-2xl border border-gray-200 p-6 hover:border-[#1a3a2a] hover:shadow-md transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 flex items-center justify-center group-hover:bg-[#1a3a2a] transition-colors flex-shrink-0">
              <Users className="w-5 h-5 text-[#1a3a2a] group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900 mb-1 group-hover:text-[#1a3a2a] transition-colors">View All Customers</h2>
              <p className="text-sm text-gray-500 leading-relaxed">Browse customers, generate docs, and send signing links via email.</p>
            </div>
          </button>

          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-4 bg-white rounded-2xl border border-gray-200 p-6 hover:border-[#1a3a2a] hover:shadow-md transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 flex items-center justify-center group-hover:bg-[#1a3a2a] transition-colors flex-shrink-0">
              <FileText className="w-5 h-5 text-[#1a3a2a] group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900 mb-1 group-hover:text-[#1a3a2a] transition-colors">Generate Documents</h2>
              <p className="text-sm text-gray-500 leading-relaxed">Auto-generate Annexure, WCR, DCR, and all required regulatory documents.</p>
            </div>
          </button>
        </div>
      </div>
    </div>
  )
}
