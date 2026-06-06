import { useState, useEffect, useCallback } from 'react'
import { UserPlus, Search, RefreshCw, Users } from 'lucide-react'
import { getCustomers } from '../api/customers'
import CustomerModal from '../components/CustomerModal'
import CustomerTable from '../components/CustomerTable'
import toast from 'react-hot-toast'

export default function CustomersPage() {
  const [customers, setCustomers] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [editCustomer, setEditCustomer] = useState(null)
  const LIMIT = 20

  const fetchCustomers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getCustomers({ search, page, limit: LIMIT })
      setCustomers(res.data.data)
      setTotal(res.data.total)
    } catch {
      toast.error('Failed to load customers')
    } finally {
      setLoading(false)
    }
  }, [search, page])

  useEffect(() => {
    fetchCustomers()
  }, [fetchCustomers])

  useEffect(() => {
    setPage(1)
  }, [search])

  function openAdd() {
    setEditCustomer(null)
    setShowModal(true)
  }

  function openEdit(customer) {
    setEditCustomer(customer)
    setShowModal(true)
  }

  function onSaved() {
    setShowModal(false)
    fetchCustomers()
  }

  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-xl bg-[#1a3a2a] flex items-center justify-center shadow-sm">
              <Users className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Customers</h1>
              <p className="text-sm text-gray-500 mt-0.5">
                {total} {total === 1 ? 'customer' : 'customers'} total
              </p>
            </div>
          </div>
          <button
            onClick={openAdd}
            className="flex items-center justify-center gap-2 w-full sm:w-auto px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] transition-colors shadow-sm"
          >
            <UserPlus className="w-4 h-4" />
            Add Customer
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-5">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name, app no, or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 focus:border-[#1a3a2a] transition-all shadow-sm"
          />
        </div>

        {/* Table Card */}
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 gap-3">
              <RefreshCw className="w-6 h-6 text-[#1a3a2a] animate-spin" />
              <p className="text-sm text-gray-400">Loading customers…</p>
            </div>
          ) : customers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
                <Users className="w-6 h-6 text-gray-400" />
              </div>
              <p className="text-gray-600 font-medium mb-1">No customers found</p>
              <p className="text-sm text-gray-400 mb-4">
                {search ? 'Try a different search term' : 'Get started by adding your first customer'}
              </p>
              {!search && (
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
            <CustomerTable
              customers={customers}
              onEdit={openEdit}
              onRefresh={fetchCustomers}
            />
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500">
              Page <span className="font-medium text-gray-700">{page}</span> of{' '}
              <span className="font-medium text-gray-700">{totalPages}</span>
            </p>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="px-4 py-2 text-sm font-medium border border-gray-200 rounded-xl bg-white disabled:opacity-40 hover:border-[#1a3a2a] hover:text-[#1a3a2a] transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
                className="px-4 py-2 text-sm font-medium border border-gray-200 rounded-xl bg-white disabled:opacity-40 hover:border-[#1a3a2a] hover:text-[#1a3a2a] transition-colors"
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
