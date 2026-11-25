import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Lock, Mail, User, AtSign, MailCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { login, register, verifyRegistration } from '../api/auth'
import { homePath } from '../utils/access'
import { apiError, passwordProblem, suggestEmail, usernameProblem } from '../utils/authForm'
import {
  AuthShell, CodeInput, Field, PasswordInput, PrimaryButton, TextButton, inputClass,
} from '../components/AuthUI'
import { useCooldown } from '../utils/useCooldown'

// mode: 'login' | 'signup' | 'verify' (enter the code emailed at sign-up)
export default function LoginPage() {
  const [mode, setMode] = useState('login')
  const [identifier, setIdentifier] = useState('')
  const [name, setName] = useState('')
  const [username, setUsernameValue] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [code, setCode] = useState('')
  const [sentTo, setSentTo] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldown, startCooldown] = useCooldown()
  const { setUser } = useAuth()
  const navigate = useNavigate()

  const emailSuggestion = mode === 'signup' ? suggestEmail(email) : null

  function switchMode(next) {
    setMode(next)
    setPassword('')
    setConfirm('')
    setCode('')
  }

  function finish(user) {
    setUser(user)
    navigate(homePath(user), { replace: true })
  }

  async function handleLogin(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await login(identifier.trim(), password)
      finish(res.data.data)
    } catch (err) {
      toast.error(apiError(err, 'Incorrect email/username or password'))
    } finally {
      setLoading(false)
    }
  }

  async function sendSignupCode() {
    const res = await register({ name: name.trim(), username: username.trim(), email: email.trim(), password })
    setSentTo(res.data.data.email)
    startCooldown()
    toast.success(res.data.message)
  }

  async function handleSignup(e) {
    e.preventDefault()
    const problem = name.trim().length < 2 ? 'Please enter your full name'
      : usernameProblem(username) || passwordProblem(password)
        || (password !== confirm ? "The passwords don't match" : null)
    if (problem) {
      toast.error(problem)
      return
    }
    setLoading(true)
    try {
      await sendSignupCode()
      setCode('')
      setMode('verify')
    } catch (err) {
      toast.error(apiError(err, 'Sign-up failed'))
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await verifyRegistration(sentTo, code)
      toast.success('Account created')
      finish(res.data.data)
    } catch (err) {
      toast.error(apiError(err, 'That code is incorrect'))
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  async function resend() {
    setLoading(true)
    try {
      await sendSignupCode()
    } catch (err) {
      toast.error(apiError(err, "Couldn't resend the code"))
    } finally {
      setLoading(false)
    }
  }

  if (mode === 'verify') {
    return (
      <AuthShell title="Check your email" subtitle={null}>
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 dark:border-emerald-500/20 bg-emerald-50 dark:bg-emerald-500/10 px-4 py-3 mb-6 mt-4">
          <MailCheck className="w-5 h-5 text-emerald-700 dark:text-emerald-300 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-emerald-900 dark:text-emerald-200">
            We sent a 6-digit code to <strong className="break-all">{sentTo}</strong>. Enter it below to finish creating
            your account. It expires in 10 minutes.
          </p>
        </div>
        <form onSubmit={handleVerify} className="space-y-4">
          <CodeInput value={code} onChange={setCode} />
          <PrimaryButton loading={loading} loadingText="Checking…" disabled={loading || code.length !== 6}>
            Create account
          </PrimaryButton>
        </form>
        <div className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6 space-y-2">
          <p>
            Didn&apos;t get it? Check spam, or{' '}
            <TextButton onClick={resend} disabled={loading || cooldown > 0}>
              {cooldown > 0 ? `resend in ${cooldown}s` : 'resend the code'}
            </TextButton>
          </p>
          <p>
            Wrong email?{' '}
            <TextButton onClick={() => switchMode('signup')}>Go back and fix it</TextButton>
          </p>
        </div>
      </AuthShell>
    )
  }

  const isSignup = mode === 'signup'

  return (
    <AuthShell
      title={isSignup ? 'Create account' : 'Sign in'}
      subtitle={isSignup
        ? "We'll email you a code to confirm your address before the account is created."
        : 'Sign in with your email or username.'}
    >
      {isSignup ? (
        <form onSubmit={handleSignup} className="space-y-4" noValidate>
          <Field label="Full name" icon={User}>
            <input type="text" required value={name} onChange={(e) => setName(e.target.value)}
              autoComplete="name" className={inputClass} placeholder="John Smith" />
          </Field>
          <Field label="Username" icon={AtSign} hint="3-30 characters: letters, numbers, . _ - (you can sign in with it)">
            <input type="text" required value={username}
              onChange={(e) => setUsernameValue(e.target.value.toLowerCase().replace(/\s/g, ''))}
              autoComplete="username" autoCapitalize="none" spellCheck={false}
              className={inputClass} placeholder="john.smith" />
          </Field>
          <Field
            label="Email address"
            icon={Mail}
            hint={emailSuggestion && (
              <span className="text-amber-700 dark:text-amber-300">
                Did you mean{' '}
                <TextButton onClick={() => setEmail(emailSuggestion)}>{emailSuggestion}</TextButton>?
              </span>
            )}
          >
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              autoComplete="email" autoCapitalize="none" spellCheck={false}
              className={inputClass} placeholder="you@example.com" />
          </Field>
          <Field label="Password" icon={Lock} hint="At least 8 characters">
            <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" />
          </Field>
          <Field label="Confirm password" icon={Lock}>
            <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" />
          </Field>
          <PrimaryButton loading={loading} loadingText="Sending code…">Send verification code</PrimaryButton>
        </form>
      ) : (
        <form onSubmit={handleLogin} className="space-y-4">
          <Field label="Email or username" icon={User}>
            <input type="text" required value={identifier} onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus
              className={inputClass} placeholder="you@example.com or username" />
          </Field>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">Password</label>
              <Link to="/forgot-password" className="text-xs font-semibold text-[#1a3a2a] dark:text-emerald-400 hover:underline">
                Forgot password?
              </Link>
            </div>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
              <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" />
            </div>
          </div>
          <PrimaryButton loading={loading} loadingText="Signing in…">Sign in</PrimaryButton>
        </form>
      )}

      <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
        {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
        <TextButton onClick={() => switchMode(isSignup ? 'login' : 'signup')}>
          {isSignup ? 'Sign in' : 'Sign up'}
        </TextButton>
      </p>
    </AuthShell>
  )
}
