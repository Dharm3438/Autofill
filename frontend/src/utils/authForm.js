// Shared helpers for the sign-in / sign-up / account forms.

export const SERVER_UNREACHABLE =
  "We couldn't reach the server for several minutes. Please check your internet connection and try again."

// Error text from an API failure. The backend sends one readable sentence in
// `detail`; anything else falls back to `fallback`.
export function apiError(err, fallback = 'Something went wrong') {
  // The app already waited minutes for the server (api/serverWake.js).
  if (err?.serverUnavailable) return SERVER_UNREACHABLE
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg.replace(/^Value error, /, '')
  if (!err?.response) return 'Network error. Check your connection and try again.'
  // No reason from our backend: the request never got a proper answer (server
  // waking up / restarting, proxy error). Say so, with the code, instead of
  // the page's fallback — which for login would wrongly blame the password.
  const status = err.response.status
  if (status >= 500) {
    return `The server didn't respond properly (error ${status}). It may be starting up — please try again in a minute.`
  }
  // Our own limits (e.g. sign-in lockout) always send a sentence in `detail`,
  // handled above. A bare 429 comes from the hosting edge, not from too many
  // wrong passwords — so don't say "too many attempts".
  if (status === 429) return 'The server is busy right now. Please try again in a minute.'
  return `${fallback} (error ${status})`
}

// Same rules as the backend (models/user.py), checked early for quick feedback.
export const USERNAME_RULE = /^[a-z][a-z0-9._-]{2,29}$/

export function usernameProblem(value) {
  const v = value.trim().toLowerCase()
  if (!v) return 'Choose a username'
  if (!USERNAME_RULE.test(v)) {
    return 'Username: 3-30 characters, start with a letter, only letters, numbers, . _ -'
  }
  return null
}

export function passwordProblem(value) {
  if (value.length < 8) return 'Password must be at least 8 characters'
  return null
}

// "Did you mean …@gmail.com?" for common provider typos.
const COMMON_DOMAINS = [
  'gmail.com', 'yahoo.com', 'yahoo.co.in', 'outlook.com', 'hotmail.com',
  'icloud.com', 'rediffmail.com', 'live.com',
]

function distance(a, b) {
  const dp = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)])
  for (let j = 1; j <= b.length; j++) dp[0][j] = j
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      )
    }
  }
  return dp[a.length][b.length]
}

export function suggestEmail(email) {
  const at = email.trim().lastIndexOf('@')
  if (at < 1) return null
  const local = email.trim().slice(0, at)
  const domain = email.trim().slice(at + 1).toLowerCase()
  if (!domain || COMMON_DOMAINS.includes(domain)) return null
  let best = null
  for (const d of COMMON_DOMAINS) {
    const dist = distance(domain, d)
    if (dist > 0 && dist <= 2 && (!best || dist < best.dist)) best = { d, dist }
  }
  return best ? `${local}@${best.d}` : null
}
