import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, Clock, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { homePath } from '../utils/access'

// Landing page for accounts that have signed up but have no role yet.
export default function WelcomePage() {
  const { user, refreshUser } = useAuth()
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

  return (
    <div className="min-h-[calc(100vh-60px)] bg-gray-50 dark:bg-[#0e1512] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 shadow-sm p-8 text-center">
        <div className="w-14 h-14 rounded-2xl bg-[#1a3a2a] flex items-center justify-center mx-auto mb-5">
          <Sun className="w-7 h-7 text-white" />
        </div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          Welcome{user?.name ? `, ${user.name}` : ''}!
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">
          Your account has been created. An admin will give you access shortly.
          Once they do, you'll see the pages you need here.
        </p>

        <div className="mt-6 flex items-center justify-center gap-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl px-3 py-2">
          <Clock className="w-4 h-4 flex-shrink-0" />
          Waiting for admin approval
        </div>

        <button
          onClick={checkAccess}
          disabled={checking}
          className="mt-6 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] disabled:opacity-60 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${checking ? 'animate-spin' : ''}`} />
          Check again
        </button>
      </div>
    </div>
  )
}
