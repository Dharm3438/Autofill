import { useState, useEffect, useCallback, useRef } from 'react'
import { UserPlus, Search, RefreshCw, Users } from 'lucide-react'
import { getCustomers } from '../api/customers'
import CustomerModal from '../components/CustomerModal'
import CustomerTable from '../components/CustomerTable'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { PERM } from '../utils/access'

export default function CustomersPage() {
  const { can } = useAuth()
  const canCreate = can(PERM.CUSTOMERS_CREATE)
  // Data-entry users only ever receive their own customers from the API.
  const ownOnly = !can(PERM.CUSTOMERS_READ_ALL)
  const [customers, setCustomers] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  // Debounced copy of `search` — the input updates `search` on every keystroke,
  // but we only hit the backend (an unindexed regex scan) once typing settles.
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  // True from the start so the first paint shows the spinner, not the empty state.
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editCustomer, setEditCustomer] = useState(null)
  const LIMIT = 20

  // Applying a search and resetting to page 1 happen together, so a search
  // typed on page 3 fetches once (page 1), not twice (page 3, then page 1).
  useEffect(() => {
    if (search === debouncedSearch) return
    const t = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 350)
    return () => clearTimeout(t)
  }, [search, debouncedSearch])

  // Only the newest request may update the list (an older, slower response
  // must not overwrite it).
  const requestIdRef = useRef(0)

  // The full list fetch. Only for things that change which rows are on the
  // page or the total: page/search changes, adding and deleting a customer.
  // A change to one customer updates that row in place instead (see below).
  const fetchCustomers = useCallback(async () => {
    const id = ++requestIdRef.current
    setLoading(true)
    try {
      const res = await getCustomers({ search: debouncedSearch, page, limit: LIMIT })
      if (id !== requestIdRef.current) return
      const count = res.data.total
      // A delete can empty the last page — step back instead of showing nothing.
      const lastPage = Math.max(1, Math.ceil(count / LIMIT))
      if (page > lastPage) {
        setPage(lastPage)
        return
      }
      setCustomers(res.data.data)
      setTotal(count)
    } catch {
      if (id === requestIdRef.current) toast.error('Failed to load customers')
    } finally {
      if (id === requestIdRef.current) setLoading(false)
    }
  }, [debouncedSearch, page])

  useEffect(() => {
    fetchCustomers()
  }, [fetchCustomers])

  // Replace one row with the customer as the server returned it.
  const replaceRow = useCallback((updated) => {
    setCustomers(prev => prev.map(c => (c.id === updated.id ? updated : c)))
  }, [])

  // Merge a few known fields into one row (e.g. doc_status after generation).
  const patchRow = useCallback((id, fields) => {
    setCustomers(prev => prev.map(c => (c.id === id ? { ...c, ...fields } : c)))
  }, [])

  function openAdd() {
    setEditCustomer(null)
    setShowModal(true)
  }

  function openEdit(customer) {
    setEditCustomer(customer)
    setShowModal(true)
  }

  function onSaved(saved) {
    setShowModal(false)
    // An edit returns the updated customer — swap it in, no refetch. A new
    // customer changes the total and page order, so that needs the list.
    if (editCustomer && saved) replaceRow(saved)
    else fetchCustomers()
  }

  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0e1512]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-xl bg-[#1a3a2a] flex items-center justify-center shadow-sm">
              <Users className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Customers</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                {total} {total === 1 ? 'customer' : 'customers'} {ownOnly ? 'added by you' : 'total'}
              </p>
            </div>
          </div>
          {canCreate && (
            <button
              onClick={openAdd}
              className="flex items-center justify-center gap-2 w-full sm:w-auto px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors shadow-sm"
            >
              <UserPlus className="w-4 h-4" />
              Add Customer
            </button>
          )}
        </div>

        {/* Search */}
        <div className="relative mb-5">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name, app no, or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-[#16201b] border border-gray-200 dark:border-white/10 rounded-xl text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] dark:focus:border-emerald-500/50 transition-all shadow-sm"
          />
        </div>

        {/* Table Card */}
        <div className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden shadow-sm">
          {/* Full spinner only when there's nothing on screen yet; a background
              refetch keeps the current rows visible (dimmed) so scroll position,
              expanded rows and open popups survive it. */}
          {loading && customers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 gap-3">
              <RefreshCw className="w-6 h-6 text-[#1a3a2a] dark:text-emerald-400 animate-spin" />
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading customers…</p>
            </div>
          ) : customers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-14 h-14 rounded-2xl bg-gray-100 dark:bg-white/5 flex items-center justify-center mb-4">
                <Users className="w-6 h-6 text-gray-400 dark:text-gray-500" />
              </div>
              <p className="text-gray-600 dark:text-gray-300 font-medium mb-1">No customers found</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mb-4">
                {search ? 'Try a different search term' : canCreate ? 'Get started by adding your first customer' : 'Nothing here yet'}
              </p>
              {!search && canCreate && (
                <button
                  onClick={openAdd}
                  className="flex items-center gap-2 px-4 py-2 bg-[#1a3a2a] text-white text-sm font-medium rounded-xl hover:bg-[#2d5a3d] transition-colors"
                >
                  <UserPlus className="w-4 h-4" />
                  Add Customer
                </button>
              )}
            </div>
          ) : (
            <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
              <CustomerTable
                customers={customers}
                onEdit={openEdit}
                onRefresh={fetchCustomers}
                onRowReplace={replaceRow}
                onRowPatch={patchRow}
              />
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Page <span className="font-medium text-gray-700 dark:text-gray-200">{page}</span> of{' '}
              <span className="font-medium text-gray-700 dark:text-gray-200">{totalPages}</span>
            </p>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-white/10 rounded-xl bg-white dark:bg-[#16201b] text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:border-[#1a3a2a] hover:text-[#1a3a2a] dark:hover:border-emerald-500/50 dark:hover:text-emerald-400 transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
                className="px-4 py-2 text-sm font-medium border border-gray-200 dark:border-white/10 rounded-xl bg-white dark:bg-[#16201b] text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:border-[#1a3a2a] hover:text-[#1a3a2a] dark:hover:border-emerald-500/50 dark:hover:text-emerald-400 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {showModal && (
        <CustomerModal
          customer={editCustomer}
          onClose={() => setShowModal(false)}
          onSaved={onSaved}
        />
      )}
    </div>
  )
}
