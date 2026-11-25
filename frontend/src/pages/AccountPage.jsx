import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, AtSign, BadgeCheck, KeyRound, Lock, LogOut, Mail, TriangleAlert, UserCog } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { changePassword, confirmEmailChange, logoutAll, setUsername, startEmailChange } from '../api/auth'
import { homePath } from '../utils/access'
import { apiError, passwordProblem, suggestEmail, usernameProblem } from '../utils/authForm'
import { CodeInput, Field, PasswordInput, TextButton, inputClass } from '../components/AuthUI'
import { useCooldown } from '../utils/useCooldown'

function Card({ icon: Icon, title, children }) {
  return (
    <section className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 shadow-sm p-5 sm:p-6">
      <h2 className="flex items-center gap-2 text-base font-bold text-gray-900 dark:text-gray-100 mb-4">
        <Icon className="w-4 h-4 text-[#1a3a2a] dark:text-emerald-400" />
        {title}
      </h2>
      {children}
    </section>
  )
}

function SaveButton({ loading, children, disabled }) {
  return (
    <button
      type="submit"
      disabled={loading || disabled}
      className="px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {loading ? 'Please wait…' : children}
    </button>
  )
}

function UsernameCard() {
  const { user, setUser } = useAuth()
  const [value, setValue] = useState(user?.username || '')
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

  return (
    <Card icon={AtSign} title="Username">
      <form onSubmit={save} className="space-y-3">
        <Field label="Username" icon={AtSign} hint="You can sign in with this or your email.">
          <input type="text" value={value} onChange={(e) => setValue(e.target.value.toLowerCase().replace(/\s/g, ''))}
            autoComplete="username" autoCapitalize="none" spellCheck={false} className={inputClass} />
        </Field>
        <SaveButton loading={loading} disabled={value === user?.username}>Save username</SaveButton>
      </form>
    </Card>
  )
}

function EmailCard() {
  const { user, setUser } = useAuth()
  const [step, setStep] = useState('idle') // idle | form | code
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldown, startCooldown] = useCooldown()
  const suggestion = step === 'form' ? suggestEmail(email) : null

  function open(prefill) {
    setEmail(prefill)
    setPassword('')
    setCode('')
    setStep('form')
  }

  async function send(e) {
    e?.preventDefault()
    setLoading(true)
    try {
      const res = await startEmailChange(email.trim(), password)
      toast.success(res.data.message)
      startCooldown()
      setCode('')
      setStep('code')
    } catch (err) {
      toast.error(apiError(err, "Couldn't send the code"))
    } finally {
      setLoading(false)
    }
  }

  async function confirm(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await confirmEmailChange(code)
      setUser(res.data.data)
      toast.success('Email verified')
      setStep('idle')
    } catch (err) {
      toast.error(apiError(err, 'That code is incorrect'))
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card icon={Mail} title="Email">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-sm text-gray-800 dark:text-gray-100 break-all">{user?.email}</span>
        {user?.email_verified ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20">
            <BadgeCheck className="w-3 h-3" /> Verified
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20">
            <TriangleAlert className="w-3 h-3" /> Not verified
          </span>
        )}
      </div>

      {step === 'idle' && (
        <div className="flex flex-wrap gap-3 text-sm">
          {!user?.email_verified && (
            <TextButton onClick={() => open(user.email)}>Verify this email</TextButton>
          )}
          <TextButton onClick={() => open('')}>Change email</TextButton>
        </div>
      )}

      {step === 'form' && (
        <form onSubmit={send} className="space-y-3">
          <Field
            label="Email address"
            icon={Mail}
            hint={suggestion && (
              <span className="text-amber-700 dark:text-amber-300">
                Did you mean <TextButton onClick={() => setEmail(suggestion)}>{suggestion}</TextButton>?
              </span>
            )}
          >
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              autoComplete="email" autoCapitalize="none" spellCheck={false} className={inputClass} />
          </Field>
          <Field label="Your password" icon={Lock}>
            <PasswordInput value={password} onChange={setPassword} />
          </Field>
          <div className="flex items-center gap-3">
            <SaveButton loading={loading}>Send code</SaveButton>
            <TextButton onClick={() => setStep('idle')}>Cancel</TextButton>
          </div>
        </form>
      )}

      {step === 'code' && (
        <form onSubmit={confirm} className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Enter the 6-digit code sent to <strong className="break-all">{email.trim().toLowerCase()}</strong>.
            Your email changes only after this step.
          </p>
          <CodeInput value={code} onChange={setCode} />
          <div className="flex flex-wrap items-center gap-3">
            <SaveButton loading={loading} disabled={code.length !== 6}>Confirm</SaveButton>
            <TextButton onClick={() => send()} disabled={loading || cooldown > 0}>
              {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend code'}
            </TextButton>
            <TextButton onClick={() => setStep('idle')}>Cancel</TextButton>
          </div>
        </form>
      )}
    </Card>
  )
}

function PasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)

  async function save(e) {
    e.preventDefault()
    const problem = passwordProblem(next) || (next !== confirm ? "The new passwords don't match" : null)
    if (problem) return toast.error(problem)
    setLoading(true)
    try {
      const res = await changePassword(current, next)
      toast.success(res.data.message)
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (err) {
      toast.error(apiError(err, "Couldn't change the password"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card icon={KeyRound} title="Password">
      <form onSubmit={save} className="space-y-3">
        <Field label="Current password" icon={Lock}>
          <PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" />
        </Field>
        <Field label="New password" icon={Lock} hint="At least 8 characters. Other devices will be signed out.">
          <PasswordInput value={next} onChange={setNext} autoComplete="new-password" />
        </Field>
        <Field label="Confirm new password" icon={Lock}>
          <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" />
        </Field>
        <SaveButton loading={loading}>Change password</SaveButton>
      </form>
    </Card>
  )
}

export default function AccountPage() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()

  async function signOutEverywhere() {
    if (!window.confirm('Sign out on every device, including this one?')) return
    try {
      await logoutAll()
    } catch (err) {
      toast.error(apiError(err, "Couldn't sign out other devices"))
      return
    }
    setUser(null)
    navigate('/login', { replace: true })
    toast.success('Signed out on all devices')
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512]">
      <div className="max-w-xl mx-auto px-4 py-8 space-y-5">
        <button
          onClick={() => navigate(homePath(user))}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#1a3a2a] dark:text-emerald-400 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-[#1a3a2a] flex items-center justify-center shadow-sm">
            <UserCog className="w-5 h-5 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Account</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{user?.name}</p>
          </div>
        </div>

        <UsernameCard />
        <EmailCard />
        <PasswordCard />

        <Card icon={LogOut} title="Sessions">
          <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
            Lost a phone or signed in on a shared computer? Sign out everywhere at once.
          </p>
          <button
            onClick={signOutEverywhere}
            className="px-4 py-2.5 text-sm font-semibold text-red-600 dark:text-red-300 border border-red-200 dark:border-red-500/20 rounded-xl hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
          >
            Sign out on all devices
          </button>
        </Card>
      </div>
    </div>
  )
}
