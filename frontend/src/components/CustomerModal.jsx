import { useState, useEffect } from 'react'
import { X, User2, Zap, MapPin, Gauge, UserPlus, Pencil } from 'lucide-react'
import { createCustomer, updateCustomer } from '../api/customers'
import toast from 'react-hot-toast'

const SECTIONS = [
  {
    title: 'Consumer Information',
    icon: User2,
    color: 'text-blue-600',
    bg: 'bg-blue-50',
    fields: [
      { key: 'CONSUMER_NAME',    label: 'Consumer Name',    required: true },
      { key: 'CONSUMER_ADDRESS', label: 'Address',          required: true, span: 2 },
      { key: 'CONSUMER_PHONE',   label: 'Phone',            required: true },
      { key: 'CONSUMER_EMAIL',   label: 'Email',            type: 'email' },
      { key: 'CONSUMER_AADHAR',  label: 'Aadhar Number' },
      { key: 'CONSUMER_NO',      label: 'Consumer No' },
      { key: 'CONSUMER_APP_NO',  label: 'Application No' },
      { key: 'CONSUMER_APP_DATE',label: 'Application Date', type: 'date' },
      { key: 'SANCTIONED_CAPACITY', label: 'Sanctioned Capacity' },
    ],
  },
  {
    title: 'Solar System',
    icon: Zap,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    fields: [
      { key: 'SOLAR_CAPACITY',      label: 'Solar Capacity (kW)' },
      { key: 'INVERTER_MAKE',       label: 'Inverter Make' },
      { key: 'INVERTER_CAPACITY',   label: 'Inverter Capacity' },
      { key: 'INVERTER_GURANTEE',   label: 'Inverter Guarantee' },
      { key: 'INVERTER_SR_NO',      label: 'Inverter Serial No' },
      { key: 'PANEL_COMPANY',       label: 'Panel Company' },
      { key: 'PANEL_WATT',          label: 'Panel Watt' },
      { key: 'NO_OF_PANEL',         label: 'No of Panels' },
      { key: 'TOTAL_PANEL_CAPACITY',label: 'Total Panel Capacity' },
      { key: 'PANEL_SR_NO',         label: 'Panel Serial Nos', span: 2, hint: 'Comma separated' },
      { key: 'CELL_MANUFACTURER',   label: 'Cell Manufacturer' },
      { key: 'PANEL_GURANTEE',      label: 'Panel Guarantee' },
    ],
  },
  {
    title: 'Installation',
    icon: MapPin,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    fields: [
      { key: 'INSTALLATION_DATE',        label: 'Installation Date',     type: 'date' },
      { key: 'INSTALLATION_CITY',        label: 'City' },
      { key: 'INSTALLATION_DISTRICT',    label: 'District' },
      { key: 'DISCOM_REGISTERED_OFFICE', label: 'DISCOM Registered Office', span: 2 },
      { key: 'SYSTEM_COST',              label: 'System Cost (₹)' },
    ],
  },
  {
    title: 'Meter Details',
    icon: Gauge,
    color: 'text-purple-600',
    bg: 'bg-purple-50',
    fields: [
      { key: 'METER_TESTING_DATE',   label: 'Meter Testing Date', type: 'date' },
      { key: 'METER_RECIPT_NO',      label: 'Meter Receipt No' },
      { key: 'GENERATION_METER_MAKE',label: 'Generation Meter Make' },
      { key: 'GENERATION_METER_NO',  label: 'Generation Meter No' },
    ],
  },
]

const EMPTY = SECTIONS.flatMap(s => s.fields).reduce((acc, f) => ({ ...acc, [f.key]: '' }), {})

export default function CustomerModal({ customer, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(false)
  const isEdit = Boolean(customer)

  useEffect(() => {
    if (customer) {
      const filled = { ...EMPTY }
      Object.keys(EMPTY).forEach(k => { filled[k] = customer[k] || '' })
      setForm(filled)
    }
  }, [customer])

  function set(key, val) {
    setForm(f => ({ ...f, [key]: val }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      if (isEdit) {
        await updateCustomer(customer.id, form)
        toast.success('Customer updated')
      } else {
        await createCustomer(form)
        toast.success('Customer added')
      }
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 backdrop-blur-sm overflow-y-auto py-6 px-4">
      <div className="bg-white dark:bg-[#16201b] rounded-2xl shadow-2xl w-full max-w-3xl ring-1 ring-black/10 dark:ring-white/10 my-auto">

        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-5 bg-[#1a3a2a] rounded-t-2xl">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center flex-shrink-0">
              {isEdit
                ? <Pencil className="w-5 h-5 text-white" />
                : <UserPlus className="w-5 h-5 text-white" />}
            </div>
            <div>
              <h2 className="font-semibold text-white text-base leading-tight">
                {isEdit ? 'Edit Customer' : 'Add New Customer'}
              </h2>
              <p className="text-white/60 text-xs mt-0.5">
                {isEdit ? 'Update the customer details below' : 'Fill in the customer details below'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-colors"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-5 space-y-5 max-h-[70vh] overflow-y-auto">
            {SECTIONS.map(section => {
              const Icon = section.icon
              return (
                <div key={section.title} className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden">
                  {/* Section Header */}
                  <div className={`flex items-center gap-2.5 px-4 py-3 ${section.bg} dark:bg-white/5 border-b border-gray-200 dark:border-white/10`}>
                    <div className={`w-7 h-7 rounded-lg bg-white dark:bg-white/10 flex items-center justify-center shadow-sm`}>
                      <Icon className={`w-4 h-4 ${section.color}`} />
                    </div>
                    <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">{section.title}</h3>
                  </div>

                  {/* Section Fields */}
                  <div className="p-4 bg-white dark:bg-[#16201b] grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
                    {section.fields.map(field => (
                      <div key={field.key} className={field.span === 2 ? 'sm:col-span-2' : ''}>
                        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1.5 uppercase tracking-wide">
                          {field.label}
                          {field.required && <span className="text-red-500 dark:text-red-400 ml-0.5 normal-case">*</span>}
                        </label>
                        <input
                          type={field.type || 'text'}
                          required={field.required}
                          value={form[field.key]}
                          onChange={e => set(field.key, e.target.value)}
                          placeholder={field.hint || ''}
                          className="w-full px-3 py-2.5 rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] dark:focus:border-emerald-500/50 focus:bg-white dark:focus:bg-white/10 transition-all"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 dark:border-white/10 bg-gray-50 dark:bg-white/5 rounded-b-2xl">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl hover:bg-gray-50 dark:hover:bg-white/10 hover:border-gray-300 dark:hover:border-white/20 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-xl hover:bg-[#2d5a3d] disabled:opacity-60 transition-colors shadow-sm"
            >
              {loading ? 'Saving…' : isEdit ? 'Save Changes' : 'Add Customer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}