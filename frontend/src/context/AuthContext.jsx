import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getMe } from '../api/auth'
import { hasPerm } from '../utils/access'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // Re-read the session (roles can change while someone is logged in).
  const refreshUser = useCallback(async () => {
    try {
      const res = await getMe()
      setUser(res.data.data)
      return res.data.data
    } catch {
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    getMe()
      .then((res) => setUser(res.data.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const can = useCallback((perm) => hasPerm(user, perm), [user])

  return (
    <AuthContext.Provider value={{ user, setUser, loading, can, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
