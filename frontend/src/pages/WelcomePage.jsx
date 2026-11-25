import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, Clock, RefreshCw, LogOut, UserCog } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { logout } from '../api/auth'
import { homePath } from '../utils/access'
import { VerifyEmailBanner } from '../components/AccountNotices'

// Standalone landing page for accounts with no role yet. Deliberately rendered
// WITHOUT the app Layout/Navbar, so a pending user sees no tabs, no app
// chrome, nothing but this message.
export default function WelcomePage() {
  const { user, setUser, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [checking, setChecking] = useState(false)

  async function checkAccess() {
    setChecking(true)
    const fresh = await refreshUser()
    setChecking(false)
    const home = homePath(fresh)
    if (fresh && home !== '/welcome') {
      toast.success('Access granted')
      navigate(home, { replace: true })
    } else {
      toast('No access yet. Please check back later.', { icon: '⏳' })
    }
  }

  async function handleLogout() {
    try {
      await logout()
    } catch {
      // Logging out locally is enough even if the request fails.
    }
    setUser(null)
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512] flex flex-col">
      <VerifyEmailBanner />
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 shadow-sm p-8 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[#1a3a2a] flex items-center justify-center mx-auto mb-5">
            <Sun className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            Welcome{user?.name ? `, ${user.name}` : ''}!
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">
            Your account has been created. An admin will provide you access.
            Once they do, you'll see the pages you need here.
          </p>

          <div className="mt-6 flex items-center justify-center gap-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl px-3 py-2">
            <Clock className="w-4 h-4 flex-shrink-0" />
            Waiting for admin approval
          </div>

          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={checkAccess}
              disabled={checking}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] disabled:opacity-60 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${checking ? 'animate-spin' : ''}`} />
              Check again
            </button>
            <button
              onClick={handleLogout}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-white/10 rounded-xl hover:border-[#1a3a2a] dark:hover:border-emerald-500/50 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Logout
            </button>
          </div>
          <button
            onClick={() => navigate('/account')}
            className="mt-4 inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-[#1a3a2a] dark:hover:text-emerald-400"
          >
            <UserCog className="w-4 h-4" />
            Account settings
          </button>
        </div>
      </div>
    </div>
  )
}
