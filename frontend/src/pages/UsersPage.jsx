import { useState, useEffect, useCallback, useMemo } from 'react'
import { ShieldCheck, RefreshCw, Search, Check, BadgeCheck, Pencil, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { getUsers, updateUserAccess } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { apiError, usernameProblem } from '../utils/authForm'

const ROLE_HINTS = {
  admin: 'Everything, including user management',
  data_entry: 'Add customers and edit only their own',
  installation: 'Installation steps and payments for all customers',
  documents: 'Generate, upload, print and send documents; edit customers',
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

// Admin fix for a mistyped email (so password reset reaches the person) or a username.
function EditUserModal({ user, onClose, onSaved }) {
  const [email, setEmail] = useState(user.email)
  const [username, setUsername] = useState(user.username || '')
  const [saving, setSaving] = useState(false)

  async function save(e) {
    e.preventDefault()
    const body = {}
    if (email.trim().toLowerCase() !== user.email) body.email = email.trim()
    if (username.trim().toLowerCase() !== (user.username || '')) {
      const problem = usernameProblem(username)
      if (problem) return toast.error(problem)
      body.username = username.trim()
    }
    if (!Object.keys(body).length) return onClose()
    setSaving(true)
    try {
      const res = await updateUserAccess(user.id, body)
      onSaved(res.data.data)
      toast.success(`Updated ${user.name}`)
      onClose()
    } catch (err) {
      toast.error(apiError(err, 'Failed to update user'))
    } finally {
      setSaving(false)
    }
  }

  const field = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#0e1512] text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 focus:border-[#1a3a2a]'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <form onSubmit={save} onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 shadow-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900 dark:text-gray-100">Edit {user.name}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>
        <label className="block">
          <span className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1.5">Email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
          <span className="block text-xs text-gray-500 dark:text-gray-400 mt-1.5">
            A changed email is marked unverified until the user confirms it from their Account page.
          </span>
        </label>
        <label className="block">
          <span className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1.5">Username</span>
          <input type="text" value={username}
            onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/\s/g, ''))} className={field} />
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-white/10 rounded-xl">
            Cancel
          </button>
          <button type="submit" disabled={saving}
            className="px-4 py-2 text-sm font-semibold text-white bg-[#1a3a2a] rounded-xl hover:bg-[#2d5a3d] disabled:opacity-60">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  )
}

function identity(u, onEdit) {
  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-gray-500 dark:text-gray-400 min-w-0">
      {u.username && <span className="font-medium text-gray-600 dark:text-gray-300">@{u.username}</span>}
      <span className="truncate">{u.email}</span>
      {u.email_verified ? (
        <BadgeCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" aria-label="Email verified" />
      ) : (
        <span className="px-1.5 rounded bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">unverified</span>
      )}
      <button onClick={onEdit} title="Edit email / username" aria-label={`Edit ${u.name}`}
        className="p-0.5 text-gray-400 hover:text-[#1a3a2a] dark:hover:text-emerald-400">
        <Pencil className="w-3 h-3" />
      </button>
    </div>
  )
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getUsers()
      setUsers(res.data.data)
      setRoles(res.data.roles)
    } catch {
      toast.error('Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function save(u, body, okMsg) {
    setSavingId(u.id)
    try {
      const res = await updateUserAccess(u.id, body)
      setUsers((list) => list.map((x) => (x.id === u.id ? res.data.data : x)))
      toast.success(okMsg)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update user')
    } finally {
      setSavingId(null)
    }
  }

  function toggleRole(u, roleKey) {
    const next = u.roles.includes(roleKey) ? u.roles.filter((r) => r !== roleKey) : [...u.roles, roleKey]
    save(u, { roles: next }, `Updated access for ${u.name}`)
  }

  function toggleActive(u) {
    save(u, { is_active: !u.is_active }, u.is_active ? `${u.name} disabled` : `${u.name} enabled`)
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = q
      ? users.filter((u) => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)
          || (u.username || '').includes(q))
      : users
    // Accounts waiting for access first.
    return [...list].sort((a, b) => (a.roles.length === 0 ? 0 : 1) - (b.roles.length === 0 ? 0 : 1))
  }, [users, search])

  const pendingCount = users.filter((u) => u.roles.length === 0 && u.is_active).length

  function roleChips(u) {
    const busy = savingId === u.id
    return (
      <div className="flex flex-wrap gap-1.5">
        {roles.map((r) => {
          const on = u.roles.includes(r.key)
          return (
            <button
              key={r.key}
              title={ROLE_HINTS[r.key]}
              disabled={busy}
              onClick={() => toggleRole(u, r.key)}
              aria-pressed={on}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors disabled:opacity-50 ${
                on
                  ? 'bg-[#1a3a2a] text-white border-[#1a3a2a] dark:bg-emerald-600 dark:border-emerald-600'
                  : 'bg-white text-gray-500 border-gray-200 hover:border-[#1a3a2a] hover:text-[#1a3a2a] dark:bg-white/5 dark:text-gray-400 dark:border-white/10 dark:hover:border-emerald-500/50 dark:hover:text-emerald-400'
              }`}
            >
              {on && <Check className="w-3 h-3" />}
              {r.label}
            </button>
          )
        })}
      </div>
    )
  }

  function statusCell(u) {
    const isMe = u.id === me?.id
    return (
      <div className="flex items-center gap-2">
        {u.roles.length === 0 && u.is_active && (
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20">
            Pending
          </span>
        )}
        <button
          onClick={() => toggleActive(u)}
          disabled={savingId === u.id || isMe}
          title={isMe ? "You can't disable your own account" : u.is_active ? 'Disable account' : 'Enable account'}
          className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
            u.is_active
              ? 'text-gray-600 border-gray-200 hover:border-red-300 hover:text-red-600 dark:text-gray-300 dark:border-white/10 dark:hover:text-red-400'
              : 'text-red-600 border-red-200 bg-red-50 hover:bg-red-100 dark:text-red-300 dark:border-red-500/20 dark:bg-red-500/10'
          }`}
        >
          {u.is_active ? 'Active' : 'Disabled'}
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-xl bg-[#1a3a2a] flex items-center justify-center shadow-sm">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Users &amp; Access</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                {users.length} {users.length === 1 ? 'user' : 'users'}
                {pendingCount > 0 && ` · ${pendingCount} waiting for access`}
              </p>
            </div>
          </div>
          <button
            onClick={load}
            className="flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-200 dark:border-white/10 bg-white dark:bg-[#16201b] text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl hover:border-[#1a3a2a] dark:hover:border-emerald-500/50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        <div className="relative mb-5">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name, username or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] transition-all shadow-sm"
          />
        </div>

        <div className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden shadow-sm">
          {loading && users.length === 0 ? (
            <div className="flex items-center justify-center py-24">
              <RefreshCw className="w-6 h-6 text-[#1a3a2a] dark:text-emerald-400 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-center text-sm text-gray-500 dark:text-gray-400 py-24">No users found</p>
          ) : (
            <>
              {/* Desktop */}
              <table className="hidden md:table w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-white/5 border-b-2 border-gray-100 dark:border-white/10">
                    <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">User</th>
                    <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Joined</th>
                    <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Roles</th>
                    <th className="text-left px-5 py-3.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-white/10">
                  {filtered.map((u) => (
                    <tr key={u.id} className={u.is_active ? '' : 'opacity-60'}>
                      <td className="px-5 py-4">
                        <p className="font-semibold text-gray-800 dark:text-gray-100">
                          {u.name}{u.id === me?.id && <span className="ml-1.5 text-xs font-normal text-gray-400">(you)</span>}
                        </p>
                        {identity(u, () => setEditing(u))}
                      </td>
                      <td className="px-5 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">{formatDate(u.created_at)}</td>
                      <td className="px-5 py-4">{roleChips(u)}</td>
                      <td className="px-5 py-4">{statusCell(u)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Mobile */}
              <div className="md:hidden divide-y divide-gray-100 dark:divide-white/10">
                {filtered.map((u) => (
                  <div key={u.id} className={`p-4 space-y-3 ${u.is_active ? '' : 'opacity-60'}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-gray-800 dark:text-gray-100 truncate">
                          {u.name}{u.id === me?.id && <span className="ml-1.5 text-xs font-normal text-gray-400">(you)</span>}
                        </p>
                        {identity(u, () => setEditing(u))}
                      </div>
                      {statusCell(u)}
                    </div>
                    {roleChips(u)}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {editing && (
          <EditUserModal
            user={editing}
            onClose={() => setEditing(null)}
            onSaved={(saved) => setUsers((list) => list.map((x) => (x.id === saved.id ? saved : x)))}
          />
        )}

        <p className="text-xs text-gray-400 dark:text-gray-500 mt-4">
          A user can hold several roles. Changes take effect on their next action, with no need to log out.
          New sign-ups appear here as <span className="font-medium">Pending</span> and see only a welcome page until you assign a role.
          Every new account has already confirmed its email with a code.
        </p>
      </div>
    </div>
  )
}
