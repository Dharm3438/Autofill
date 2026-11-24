import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { homePath } from '../utils/access'

// `perm` (string or any-of array) is optional: without it the route only needs
// a logged-in user. Users lacking the permission are sent to their own landing
// page. This is purely navigation — the API enforces access independently.
export default function ProtectedRoute({ perm, children }) {
  const { user, loading, can } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[#1a3a2a] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />
  if (perm && !can(perm)) return <Navigate to={homePath(user)} replace />
  return children
}

export function HomeRedirect() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? homePath(user) : '/login'} replace />
}
