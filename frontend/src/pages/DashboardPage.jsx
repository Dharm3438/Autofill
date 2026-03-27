import { useNavigate } from 'react-router-dom'
import { Users, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()

  return (
    <div className="min-h-screen bg-[#f7f7f5] p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-semibold text-[#0f1117] mb-2">
          Welcome, {user?.name} 👋
        </h1>
        <p className="text-sm text-[#5a5f72] mb-8">What would you like to do?</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-5 bg-white rounded-2xl border border-[#dddbd8] p-6 hover:border-[#1a3a2a] hover:shadow-md transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 flex items-center justify-center group-hover:bg-[#1a3a2a] transition-colors flex-shrink-0">
              <UserPlus className="w-5 h-5 text-[#1a3a2a] group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-[#0f1117] mb-1">Add Customer</h2>
              <p className="text-sm text-[#5a5f72]">Enter new solar installation customer details</p>
            </div>
          </button>

          <button
            onClick={() => navigate('/customers')}
            className="group flex items-start gap-5 bg-white rounded-2xl border border-[#dddbd8] p-6 hover:border-[#1a3a2a] hover:shadow-md transition-all text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-[#1a3a2a]/10 flex items-center justify-center group-hover:bg-[#1a3a2a] transition-colors flex-shrink-0">
              <Users className="w-5 h-5 text-[#1a3a2a] group-hover:text-white transition-colors" />
            </div>
            <div>
              <h2 className="font-semibold text-[#0f1117] mb-1">View All Customers</h2>
              <p className="text-sm text-[#5a5f72]">Manage customers, generate docs, send signing links</p>
            </div>
          </button>
        </div>
      </div>
    </div>
  )
}
