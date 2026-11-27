import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { getMe } from '../api/auth'
import { hasPerm } from '../utils/access'

const AuthContext = createContext(null)

// Only a 401 means "not signed in". Anything else (server asleep for longer
// than the app waits, a 500, …) says nothing about the session, so the user is
// NOT treated as signed out — that used to bounce people with a valid login to
// the login screen whenever the backend was waking up.
const isSignedOut = (err) => err?.response?.status === 401

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  // Latest user, for refreshUser's fallback (a stale closure could hand back old roles).
  const userRef = useRef(null)
  useEffect(() => { userRef.current = user }, [user])
  // Set when /auth/me failed for a reason other than "not signed in".
  const [unreachable, setUnreachable] = useState(false)

  const loadUser = useCallback(async () => {
    try {
      const res = await getMe()
      setUser(res.data.data)
      setUnreachable(false)
      return res.data.data
    } catch (err) {
      if (isSignedOut(err)) {
        setUser(null)
        setUnreachable(false)
        return null
      }
      setUnreachable(true)
      throw err
    }
  }, [])

  useEffect(() => {
    loadUser().catch(() => {}).finally(() => setLoading(false))
  }, [loadUser])

  // Re-read the session (roles can change while someone is logged in). On a
  // non-401 failure the current user is kept.
  const refreshUser = useCallback(async () => {
    try {
      return await loadUser()
    } catch {
      setUnreachable(false) // keep the page as it is; the caller decides what to show
      return userRef.current
    }
  }, [loadUser])

  // "Try again" on the can't-reach-the-server screen.
  const retry = useCallback(async () => {
    setLoading(true)
    try {
      await loadUser()
    } catch {
      // still unreachable; the screen stays
    } finally {
      setLoading(false)
    }
  }, [loadUser])

  const can = useCallback((perm) => hasPerm(user, perm), [user])

  return (
    <AuthContext.Provider value={{ user, setUser, loading, unreachable, retry, can, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
