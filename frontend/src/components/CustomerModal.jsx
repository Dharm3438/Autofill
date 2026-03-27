import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { createCustomer, updateCustomer } from '../api/customers'
import toast from 'react-hot-toast'

const SECTIONS = [
  {
    title: 'Consumer Information',
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
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 overflow-y-auto py-8 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl">

        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#eeecea] sticky top-0 bg-white rounded-t-2xl z-10">
          <h2 className="font-semibold text-[#0f1117] text-lg">
            {isEdit ? 'Edit Customer' : 'Add New Customer'}
          </h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors">
            <X className="w-5 h-5 text-[#5a5f72]" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-5 space-y-8">
            {SECTIONS.map(section => (
              <div key={section.title}>
                <h3 className="text-xs font-semibold text-[#1a3a2a] uppercase tracking-wider mb-3">
                  {section.title}
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  {section.fields.map(field => (
                    <div key={field.key} className={field.span === 2 ? 'col-span-2' : ''}>
                      <label className="block text-xs font-medium text-[#5a5f72] mb-1">
                        {field.label}
                        {field.required && <span className="text-red-500 ml-0.5">*</span>}
                      </label>
                      <input
                        type={field.type || 'text'}
                        required={field.required}
                        value={form[field.key]}
                        onChange={e => set(field.key, e.target.value)}
                        placeholder={field.hint || ''}
                        className="w-full px-3 py-2 rounded-lg border border-[#dddbd8] bg-[#f7f7f5] text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a2a] focus:border-transparent"
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#eeecea] sticky bottom-0 bg-white rounded-b-2xl">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-[#5a5f72] hover:text-[#0f1117] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 bg-[#1a3a2a] text-white text-sm font-medium rounded-xl hover:bg-[#2d6647] disabled:opacity-60 transition-colors"
            >
              {loading ? 'Saving…' : isEdit ? 'Save Changes' : 'Add Customer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
