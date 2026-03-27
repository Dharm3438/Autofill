import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { logout } from '../api/auth'
import { LogOut, LayoutDashboard, Users } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Navbar() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    try {
      await logout()
    } catch (_) {}
    setUser(null)
    navigate('/login')
    toast.success('Logged out')
  }

  return (
    <nav className="bg-[#1a3a2a] text-white px-6 py-3 flex items-center justify-between sticky top-0 z-50 shadow-md">
      <div className="flex items-center gap-6">
        <span className="font-semibold text-lg tracking-tight">Solar Docs</span>
        <div className="hidden sm:flex items-center gap-1">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm hover:bg-white/10 transition-colors"
          >
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </button>
          <button
            onClick={() => navigate('/customers')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm hover:bg-white/10 transition-colors"
          >
            <Users className="w-4 h-4" />
            Customers
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-white/70 hidden sm:block">{user?.name || user?.email}</span>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm hover:bg-white/10 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </nav>
  )
}
