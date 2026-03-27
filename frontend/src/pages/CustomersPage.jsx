import { useState, useEffect, useCallback } from 'react'
import { UserPlus, Search, RefreshCw } from 'lucide-react'
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

  // Reset to page 1 when search changes
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
    <div className="min-h-screen bg-[#f7f7f5]">
      <div className="max-w-7xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-[#0f1117]">Customers</h1>
            <p className="text-sm text-[#5a5f72] mt-0.5">{total} total customers</p>
          </div>
          <button
            onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-medium rounded-xl hover:bg-[#2d6647] transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            Add Customer
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-5">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9399aa]" />
          <input
            type="text"
            placeholder="Search by name, app no, or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-[#dddbd8] rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a2a] focus:border-transparent"
          />
        </div>

        {/* Table */}
        <div className="bg-white rounded-2xl border border-[#dddbd8] overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="w-6 h-6 text-[#1a3a2a] animate-spin" />
            </div>
          ) : customers.length === 0 ? (
            <div className="text-center py-20">
              <p className="text-[#5a5f72] text-sm">No customers found.</p>
              <button onClick={openAdd} className="mt-3 text-sm text-[#1a3a2a] font-medium hover:underline">
                Add your first customer
              </button>
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
            <p className="text-sm text-[#5a5f72]">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="px-3 py-1.5 text-sm border border-[#dddbd8] rounded-lg disabled:opacity-40 hover:border-[#1a3a2a] transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
                className="px-3 py-1.5 text-sm border border-[#dddbd8] rounded-lg disabled:opacity-40 hover:border-[#1a3a2a] transition-colors"
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
