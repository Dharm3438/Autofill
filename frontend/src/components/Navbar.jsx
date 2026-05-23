import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { logout } from '../api/auth'
import { LogOut, LayoutDashboard, Users, Sun } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Navbar() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  async function handleLogout() {
    try {
      await logout()
    } catch (_) {}
    setUser(null)
    navigate('/login')
    toast.success('Logged out')
  }

  function navBtn(path, Icon, label) {
    const active = location.pathname === path
    return (
      <button
        onClick={() => navigate(path)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
          active
            ? 'bg-white/20 text-white'
            : 'text-white/70 hover:bg-white/10 hover:text-white'
        }`}
      >
        <Icon className="w-4 h-4" />
        {label}
      </button>
    )
  }

  return (
    <nav className="bg-[#1a3a2a] text-white px-6 py-3 flex items-center justify-between sticky top-0 z-50 shadow-md">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-white/15 flex items-center justify-center">
            <Sun className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white tracking-tight">Solar Docs</span>
        </div>
        <div className="hidden sm:flex items-center gap-1">
          {navBtn('/dashboard', LayoutDashboard, 'Dashboard')}
          {navBtn('/customers', Users, 'Customers')}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {user?.name && (
          <div className="hidden sm:flex items-center gap-2 bg-white/10 rounded-lg px-3 py-1.5">
            <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-xs font-bold text-white">
              {(user.name || user.email || '?')[0].toUpperCase()}
            </div>
            <span className="text-sm text-white/90 font-medium">{user.name || user.email}</span>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-white/70 hover:bg-white/10 hover:text-white transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </nav>
  )
}
