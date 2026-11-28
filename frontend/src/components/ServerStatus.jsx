import { useEffect, useState } from 'react'
import { Loader2, WifiOff, RefreshCw } from 'lucide-react'
import { getSlowState, subscribeSlowRequests } from '../api/slowRequests'

function useSlowRequests() {
  const [state, setState] = useState(getSlowState)
  useEffect(() => subscribeSlowRequests(setState), [])
  return state
}

function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

function useElapsed(since) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!since) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [since])
  return since ? Math.max(0, Math.floor((now - since) / 1000)) : 0
}

const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

// Shown while a request has been waiting more than a few seconds — usually
// Render's free plan starting the backend after an idle spell. Render holds
// the request and answers it once the server is up; nothing is re-sent.
export function ServerStatusBanner() {
  const { slow, since } = useSlowRequests()
  const online = useOnline()
  const elapsed = useElapsed(slow ? since : null)

  if (!slow) return null

  const title = online ? 'Waiting for the server…' : 'You appear to be offline'
  const detail = !online
    ? 'Please check your internet connection.'
    : 'If the server was idle it is starting up — this can take a minute or two. Please keep this page open.'

  return (
    <div role="status" aria-live="polite"
      className="fixed inset-x-0 top-0 z-[60] flex justify-center px-4 pt-3 pointer-events-none">
      <div className="pointer-events-auto flex items-start gap-3 max-w-xl w-full rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-[#2a2210] px-4 py-3 shadow-lg">
        {online
          ? <Loader2 className="w-5 h-5 mt-0.5 flex-shrink-0 animate-spin text-amber-700 dark:text-amber-300" />
          : <WifiOff className="w-5 h-5 mt-0.5 flex-shrink-0 text-amber-700 dark:text-amber-300" />}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-100">
            {title} <span className="font-normal tabular-nums text-amber-700 dark:text-amber-300">{clock(elapsed)}</span>
          </p>
          <p className="text-xs text-amber-800 dark:text-amber-200/90 mt-0.5">{detail}</p>
        </div>
      </div>
    </div>
  )
}

// Full-page fallback when the session couldn't be checked (no answer, or a
// server error). This is not a sign-out: "Try again" re-checks the session.
export function ServerUnreachable({ onRetry }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-[#0e1512] px-4">
      <div className="max-w-md w-full text-center rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] p-8 shadow-sm">
        <WifiOff className="w-10 h-10 mx-auto text-gray-400 dark:text-gray-500" />
        <h1 className="mt-4 text-lg font-bold text-gray-900 dark:text-gray-100">Can&apos;t reach the server</h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          The server didn&apos;t answer. Please check your internet connection and try again.
        </p>
        <button type="button" onClick={onRetry}
          className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#1a3a2a] text-white text-sm font-semibold hover:bg-[#2d5a3d] transition-colors">
          <RefreshCw className="w-4 h-4" /> Try again
        </button>
      </div>
    </div>
  )
}
