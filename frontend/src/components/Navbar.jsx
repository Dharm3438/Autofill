import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { logout } from '../api/auth'
import { LogOut, LayoutDashboard, Users, Sun, Moon, Menu, X } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Navbar() {
  const { user, setUser } = useAuth()
  const { isDark, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  async function handleLogout() {
    try {
      await logout()
    } catch (_) {}
    setUser(null)
    navigate('/login')
    toast.success('Logged out')
  }

  function go(path) {
    navigate(path)
    setMenuOpen(false)
  }

  const links = [
    { path: '/dashboard', Icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/customers', Icon: Users, label: 'Customers' },
  ]

  function navBtn({ path, Icon, label }) {
    const active = location.pathname === path
    return (
      <button
        key={path}
        onClick={() => go(path)}
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
    <nav className="bg-[#1a3a2a] text-white sticky top-0 z-50 shadow-md">
      <div className="px-4 sm:px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-white/15 flex items-center justify-center">
              <Sun className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-white tracking-tight">Solar Docs</span>
          </div>
          <div className="hidden sm:flex items-center gap-1">
            {links.map(navBtn)}
          </div>
        </div>

        {/* Desktop right side */}
        <div className="hidden sm:flex items-center gap-3">
          <button
            onClick={toggleTheme}
            className="flex items-center justify-center w-9 h-9 rounded-lg text-white/70 hover:bg-white/10 hover:text-white transition-colors"
            title={isDark ? 'Switch to day mode' : 'Switch to night mode'}
            aria-label={isDark ? 'Switch to day mode' : 'Switch to night mode'}
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          {user?.name && (
            <div className="flex items-center gap-2 bg-white/10 rounded-lg px-3 py-1.5">
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
            <span>Logout</span>
          </button>
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMenuOpen(o => !o)}
          className="sm:hidden p-2 rounded-lg text-white/80 hover:bg-white/10 transition-colors"
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="sm:hidden border-t border-white/10 px-4 py-3 space-y-1">
          {user?.name && (
            <div className="flex items-center gap-2 px-1 py-2 mb-1">
              <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center text-sm font-bold text-white">
                {(user.name || user.email || '?')[0].toUpperCase()}
              </div>
              <span className="text-sm text-white/90 font-medium">{user.name || user.email}</span>
            </div>
          )}
          {links.map(({ path, Icon, label }) => {
            const active = location.pathname === path
            return (
              <button
                key={path}
                onClick={() => go(path)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active ? 'bg-white/20 text-white' : 'text-white/80 hover:bg-white/10 hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            )
          })}
          <button
            onClick={() => { toggleTheme(); setMenuOpen(false) }}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors"
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            {isDark ? 'Day mode' : 'Night mode'}
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </button>
        </div>
      )}
    </nav>
  )
}
