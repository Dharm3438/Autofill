import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AtSign, LogOut, Sun, TriangleAlert } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { logout, setUsername } from '../api/auth'
import { apiError, usernameProblem } from '../utils/authForm'
import { Field, PrimaryButton, inputClass } from './AuthUI'

// Accounts created before usernames existed must pick one once. Shown in place
// of any page until they do (see ProtectedRoute).
export function ChooseUsername() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [value, setValue] = useState(() => (user?.email || '').split('@')[0].toLowerCase().replace(/[^a-z0-9._-]/g, ''))
  const [loading, setLoading] = useState(false)

  async function save(e) {
    e.preventDefault()
    const problem = usernameProblem(value)
    if (problem) return toast.error(problem)
    setLoading(true)
    try {
      const res = await setUsername(value.trim())
      setUser(res.data.data)
      toast.success('Username saved')
    } catch (err) {
      toast.error(apiError(err, "Couldn't save the username"))
    } finally {
      setLoading(false)
    }
  }

  async function handleLogout() {
    try { await logout() } catch { /* local logout is enough */ }
    setUser(null)
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 shadow-sm p-8">
        <div className="w-12 h-12 rounded-2xl bg-[#1a3a2a] flex items-center justify-center mx-auto mb-4">
          <Sun className="w-6 h-6 text-white" />
        </div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 text-center">Choose a username</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 mb-6 text-center leading-relaxed">
          Every account now has a username. You can sign in with it or with your email.
        </p>
        <form onSubmit={save} className="space-y-4">
          <Field label="Username" icon={AtSign} hint="3-30 characters: letters, numbers, . _ -">
            <input type="text" value={value} autoFocus
              onChange={(e) => setValue(e.target.value.toLowerCase().replace(/\s/g, ''))}
              autoComplete="username" autoCapitalize="none" spellCheck={false} className={inputClass} />
          </Field>
          <PrimaryButton loading={loading} loadingText="Saving…">Save and continue</PrimaryButton>
        </form>
        <button onClick={handleLogout}
          className="mt-5 mx-auto flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
          <LogOut className="w-4 h-4" /> Logout
        </button>
      </div>
    </div>
  )
}

// Older accounts were never asked to prove their email; until they do, a
// typo'd address would make "Forgot password" useless for them.
export function VerifyEmailBanner({ className = '' }) {
  const { user } = useAuth()
  if (!user || user.email_verified) return null
  return (
    <div className={`flex flex-wrap items-center justify-center gap-x-2 gap-y-1 px-4 py-2 text-sm bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-200 border-b border-amber-200 dark:border-amber-500/20 ${className}`}>
      <TriangleAlert className="w-4 h-4 flex-shrink-0" />
      <span>Please verify your email ({user.email}) so you can reset your password if you forget it.</span>
      <Link to="/account" className="font-semibold underline">Verify now</Link>
    </div>
  )
}
