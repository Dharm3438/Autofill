import { useState } from 'react'
import { Sun, Eye, EyeOff } from 'lucide-react'

// Building blocks shared by the sign-in, sign-up, forgot-password and account pages.

export const inputClass =
  'w-full pl-10 pr-4 py-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] ' +
  'text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none ' +
  'focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] ' +
  'dark:focus:border-emerald-500/50 transition-all shadow-sm disabled:opacity-60'

export function AuthShell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen flex bg-gray-50 dark:bg-[#0e1512]">
      <div className="hidden lg:flex flex-col justify-between w-96 bg-[#1a3a2a] dark:bg-[#13241b] p-10 flex-shrink-0">
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
        <p className="text-white/30 text-xs">Solar Document Platform &copy; {new Date().getFullYear()}</p>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 sm:p-8">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-center gap-2 mb-8 lg:hidden">
            <div className="w-10 h-10 rounded-xl bg-[#1a3a2a] flex items-center justify-center">
              <Sun className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-gray-900 dark:text-gray-100">Solar Docs</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mb-8">{subtitle}</p>}
          {children}
        </div>
      </div>
    </div>
  )
}

export function Field({ label, icon: Icon, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1.5">{label}</label>
      <div className="relative">
        {Icon && (
          <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
        )}
        {children}
      </div>
      {hint && <div className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">{hint}</div>}
    </div>
  )
}

export function PasswordInput({ value, onChange, autoComplete = 'current-password', placeholder = '••••••••', ...rest }) {
  const [show, setShow] = useState(false)
  return (
    <>
      <input
        type={show ? 'text' : 'password'}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        // With "show password" on this is a plain text box, and phone keyboards
        // would capitalise the first letter, autocorrect, or add a space after a
        // suggestion — sending a different password than the one typed.
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        placeholder={placeholder}
        className={`${inputClass} pr-11`}
        {...rest}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        aria-label={show ? 'Hide password' : 'Show password'}
        tabIndex={-1}
      >
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </>
  )
}

// One box for the 6-digit emailed code; digits only, works with the phone's
// "fill code from email/SMS" suggestion.
export function CodeInput({ value, onChange, autoFocus = true }) {
  return (
    <input
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      pattern="[0-9]{6}"
      maxLength={6}
      required
      autoFocus={autoFocus}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
      placeholder="000000"
      aria-label="6-digit code"
      className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] text-center text-2xl font-bold tracking-[0.5em] text-[#1a3a2a] dark:text-emerald-300 placeholder-gray-300 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] shadow-sm font-mono"
    />
  )
}

export function PrimaryButton({ loading, loadingText, children, ...rest }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="w-full py-3 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors disabled:opacity-60 disabled:cursor-not-allowed shadow-sm mt-2"
      {...rest}
    >
      {loading ? loadingText : children}
    </button>
  )
}

export function TextButton({ children, className = '', ...rest }) {
  return (
    <button
      type="button"
      className={`text-[#1a3a2a] dark:text-emerald-400 font-semibold hover:underline disabled:opacity-50 disabled:no-underline ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
