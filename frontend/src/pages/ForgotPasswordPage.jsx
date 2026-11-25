import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Lock, User, MailCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { forgotPassword, resetPassword } from '../api/auth'
import { apiError, passwordProblem } from '../utils/authForm'
import {
  AuthShell, CodeInput, Field, PasswordInput, PrimaryButton, TextButton, inputClass,
} from '../components/AuthUI'
import { useCooldown } from '../utils/useCooldown'

// Step 1: email or username -> a code is emailed (if the account exists).
// Step 2: code + new password.
export default function ForgotPasswordPage() {
  const [step, setStep] = useState('request')
  const [identifier, setIdentifier] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldown, startCooldown] = useCooldown()
  const navigate = useNavigate()

  async function sendCode() {
    const res = await forgotPassword(identifier.trim())
    startCooldown()
    toast.success(res.data.message, { duration: 6000 })
  }

  async function handleRequest(e) {
    e.preventDefault()
    setLoading(true)
    try {
      await sendCode()
      setStep('reset')
    } catch (err) {
      toast.error(apiError(err, "Couldn't send the code"))
    } finally {
      setLoading(false)
    }
  }

  async function resend() {
    setLoading(true)
    try {
      await sendCode()
    } catch (err) {
      toast.error(apiError(err, "Couldn't send the code"))
    } finally {
      setLoading(false)
    }
  }

  async function handleReset(e) {
    e.preventDefault()
    const problem = passwordProblem(password) || (password !== confirm ? "The passwords don't match" : null)
    if (problem) {
      toast.error(problem)
      return
    }
    setLoading(true)
    try {
      const res = await resetPassword(identifier.trim(), code, password)
      toast.success(res.data.message)
      navigate('/login', { replace: true })
    } catch (err) {
      toast.error(apiError(err, 'That code is incorrect'))
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  const back = (
    <Link to="/login" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#1a3a2a] dark:text-emerald-400 hover:underline mt-6">
      <ArrowLeft className="w-4 h-4" /> Back to sign in
    </Link>
  )

  if (step === 'request') {
    return (
      <AuthShell title="Forgot password" subtitle="Enter your email or username and we'll email you a 6-digit code.">
        <form onSubmit={handleRequest} className="space-y-4">
          <Field label="Email or username" icon={User}>
            <input type="text" required value={identifier} onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus
              className={inputClass} placeholder="you@example.com or username" />
          </Field>
          <PrimaryButton loading={loading} loadingText="Sending…">Send code</PrimaryButton>
        </form>
        {back}
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Choose a new password" subtitle={null}>
      <div className="flex items-start gap-3 rounded-xl border border-emerald-200 dark:border-emerald-500/20 bg-emerald-50 dark:bg-emerald-500/10 px-4 py-3 mb-6 mt-4">
        <MailCheck className="w-5 h-5 text-emerald-700 dark:text-emerald-300 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-emerald-900 dark:text-emerald-200">
          If <strong className="break-all">{identifier.trim()}</strong> has an account, a 6-digit code is on its way to
          the email address on that account. It expires in 10 minutes.
        </p>
      </div>
      <form onSubmit={handleReset} className="space-y-4">
        <Field label="Code from the email">
          <CodeInput value={code} onChange={setCode} />
        </Field>
        <Field label="New password" icon={Lock} hint="At least 8 characters">
          <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" />
        </Field>
        <Field label="Confirm new password" icon={Lock}>
          <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" />
        </Field>
        <PrimaryButton loading={loading} loadingText="Saving…" disabled={loading || code.length !== 6}>
          Reset password
        </PrimaryButton>
      </form>
      <div className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6 space-y-2">
        <p>
          No email?{' '}
          <TextButton onClick={resend} disabled={loading || cooldown > 0}>
            {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend the code'}
          </TextButton>
          {' · '}
          <TextButton onClick={() => { setStep('request'); setCode('') }}>Try another email/username</TextButton>
        </p>
        <p className="text-xs">
          If your account&apos;s email is wrong or you no longer have it, ask your administrator to correct it.
        </p>
      </div>
      {back}
    </AuthShell>
  )
}
