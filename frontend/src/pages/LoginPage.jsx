import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { login, register } from '../api/auth'
import { Sun, Lock, Mail, User } from 'lucide-react'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()

  function switchMode(next) {
    setMode(next)
    setName('')
    setEmail('')
    setPassword('')
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      let res
      if (mode === 'login') {
        res = await login(email, password)
      } else {
        if (name.trim().length < 2) {
          toast.error('Please enter your full name')
          return
        }
        res = await register(name.trim(), email, password)
      }
      setUser(res.data.data)
      navigate('/dashboard')
    } catch (err) {
      toast.error(err.response?.data?.detail || (mode === 'login' ? 'Invalid credentials' : 'Registration failed'))
    } finally {
      setLoading(false)
    }
  }

  const isSignup = mode === 'signup'

  return (
    <div className="min-h-screen flex bg-gray-50">
      {/* Left panel */}
      <div className="hidden lg:flex flex-col justify-between w-96 bg-[#1a3a2a] p-10 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Sun className="w-6 h-6 text-white/80" />
          <span className="text-white font-bold text-lg tracking-tight">Solar Docs</span>
        </div>
        <div>
          <h2 className="text-3xl font-bold text-white leading-tight mb-4">
            Solar Document Automation Platform
          </h2>
          <p className="text-white/60 text-sm leading-relaxed">
            Manage solar installation customers, auto-generate regulatory documents, and collect digital signatures.
          </p>
        </div>
        <p className="text-white/30 text-xs">Solar Document Platform &copy; 2025</p>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="flex items-center justify-center gap-2 mb-8 lg:hidden">
            <div className="w-10 h-10 rounded-xl bg-[#1a3a2a] flex items-center justify-center">
              <Sun className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-gray-900">Solar Docs</span>
          </div>

          <h1 className="text-2xl font-bold text-gray-900 mb-1">
            {isSignup ? 'Create account' : 'Sign in'}
          </h1>
          <p className="text-sm text-gray-500 mb-8">
            {isSignup
              ? 'Enter your details to create a new account.'
              : 'Enter your credentials to access the platform.'}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {isSignup && (
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                  Full name
                </label>
                <div className="relative">
                  <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full pl-10 pr-4 py-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 focus:border-[#1a3a2a] transition-all shadow-sm"
                    placeholder="John Smith"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                Email address
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 focus:border-[#1a3a2a] transition-all shadow-sm"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 focus:border-[#1a3a2a] transition-all shadow-sm"
                  placeholder="••••••••"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors disabled:opacity-60 disabled:cursor-not-allowed shadow-sm mt-2"
            >
              {loading ? (isSignup ? 'Creating account…' : 'Signing in…') : (isSignup ? 'Create account' : 'Sign in')}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button
              type="button"
              onClick={() => switchMode(isSignup ? 'login' : 'signup')}
              className="text-[#1a3a2a] font-semibold hover:underline"
            >
              {isSignup ? 'Sign in' : 'Sign up'}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
