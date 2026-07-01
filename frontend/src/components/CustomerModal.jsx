import { useState, useEffect } from 'react'
import { X, User2, Zap, MapPin, Gauge, UserPlus, Pencil } from 'lucide-react'
import { createCustomer, updateCustomer, checkConsumerNo } from '../api/customers'
import { DEALER_OPTIONS } from '../constants/dealers'
import toast from 'react-hot-toast'

const INVERTER_OPTIONS = [
  { label: 'UTL',     value: 'UTL',     warranty: '10 YEAR' },
  { label: 'WAAREE',  value: 'WAAREE',  warranty: '10 YEAR' },
  { label: 'APS',     value: 'APS',     warranty: '10 YEAR' },
  { label: 'KSOLARE', value: 'KSOLARE', warranty: '10 YEAR' },
  { label: 'GOODWE',  value: 'GOODWE',  warranty: '10 YEAR' },
  { label: 'Xwatt',   value: 'Xwatt',   warranty: '10 YEAR' },
  { label: 'Polycab', value: 'Polycab', warranty: '8 YEAR'  },
  { label: 'Microtek Inverter', value: 'Microtek Inverter', warranty: '10 YEAR' },
  { label: 'Pv blink', value: 'Pv blink', warranty: '10 YEAR' },
]

const PANEL_OPTIONS = [
  { label: 'UTL',     value: 'UTL',     warranty: '27 YEAR' },
  { label: 'ADANI',   value: 'ADANI',   warranty: '30 YEAR' },
  { label: 'WAAREE',  value: 'WAAREE',  warranty: '30 YEAR' },
  { label: 'TATA',    value: 'TATA',    warranty: '30 YEAR' },
  { label: 'PREMIER', value: 'PREMIER', warranty: '30 YEAR' },
  { label: 'APS',     value: 'APS',     warranty: '30 YEAR' },
]

const PANEL_WATT_OPTIONS = [
  '500', '525', '530', '540', '545', '550',
  '570', '575', '580', '585', '590', '600',
  '610', '615', '620',
]

const INVERTER_CAPACITY_OPTIONS = [
  '1 kW', '2 kW', '3 kW', '3.3 kW', '3.6 kW', '4 kW', '4.6 kW',
  '5 kW', '5.5 kW', '6 kW', '8 kW', '10 kW', '12 kW', '15 kW', '20 kW',
]

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
      {
        key: 'DEALER_NAME',
        label: 'Dealer Name',
        type: 'select',
        options: DEALER_OPTIONS.map(v => ({ label: v, value: v })),
      },
      { key: 'CONSUMER_APP_NO',     label: 'Application No' },
      { key: 'CONSUMER_APP_DATE',   label: 'Application Date', type: 'date' },
      { key: 'SANCTIONED_CAPACITY', label: 'Sanctioned Capacity (kW)' },
    ],
  },
  {
    title: 'Solar System',
    icon: Zap,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    fields: [
      { key: 'SOLAR_CAPACITY', label: 'Solar Capacity (kW)' },
      {
        key: 'INVERTER_MAKE',
        label: 'Inverter Make',
        type: 'select',
        options: INVERTER_OPTIONS.map(o => ({ label: o.label, value: o.value })),
      },
      {
        key: 'INVERTER_CAPACITY',
        label: 'Inverter Capacity',
        type: 'select',
        options: INVERTER_CAPACITY_OPTIONS.map(v => ({ label: v, value: v })),
      },
      { key: 'INVERTER_GURANTEE', label: 'Inverter Guarantee', readOnly: true },
      {
        key: 'PANEL_COMPANY',
        label: 'Panel Company',
        type: 'select',
        options: PANEL_OPTIONS.map(o => ({ label: o.label, value: o.value })),
      },
      {
        key: 'PANEL_WATT',
        label: 'Panel Watt',
        type: 'select',
        options: PANEL_WATT_OPTIONS.map(v => ({ label: `${v} W`, value: v })),
      },
      { key: 'NO_OF_PANEL',          label: 'No of Panels', type: 'number' },
      { key: 'TOTAL_PANEL_CAPACITY', label: 'Total Panel Capacity (W)', readOnly: true },
      { key: 'PANEL_GURANTEE',       label: 'Panel Guarantee', readOnly: true },
    ],
  },
  {
    title: 'Installation',
    icon: MapPin,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    fields: [
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
      { key: 'METER_TESTING_DATE',    label: 'Meter Testing Date', type: 'date' },
      { key: 'METER_RECIPT_NO',       label: 'Meter Receipt No' },
      { key: 'GENERATION_METER_MAKE', label: 'Generation Meter Make' },
      { key: 'GENERATION_METER_NO',   label: 'Generation Meter No' },
    ],
  },
]

const EMPTY = SECTIONS.flatMap(s => s.fields).reduce((acc, f) => ({ ...acc, [f.key]: '' }), {})

function calcTotalCapacity(watt, qty) {
  const w = parseFloat(watt)
  const q = parseInt(qty, 10)
  return !isNaN(w) && !isNaN(q) && q > 0 ? String(w * q) : ''
}

export default function CustomerModal({ customer, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(false)
  const [consumerNoError, setConsumerNoError] = useState('')
  const isEdit = Boolean(customer)

  useEffect(() => {
    if (customer) {
      const filled = { ...EMPTY }
      Object.keys(EMPTY).forEach(k => { filled[k] = customer[k] || '' })
      setForm(filled)
    }
  }, [customer])

  function set(key, val) {
    setForm(f => {
      const next = { ...f, [key]: val }

      if (key === 'INVERTER_MAKE') {
        const inv = INVERTER_OPTIONS.find(o => o.value === val)
        next.INVERTER_GURANTEE = inv ? inv.warranty : ''
      }

      if (key === 'PANEL_COMPANY') {
        const panel = PANEL_OPTIONS.find(o => o.value === val)
        next.PANEL_GURANTEE = panel ? panel.warranty : ''
      }

      if (key === 'PANEL_WATT' || key === 'NO_OF_PANEL') {
        next.TOTAL_PANEL_CAPACITY = calcTotalCapacity(
          key === 'PANEL_WATT' ? val : f.PANEL_WATT,
          key === 'NO_OF_PANEL' ? val : f.NO_OF_PANEL,
        )
      }

      return next
    })
  }

  async function handleConsumerNoBlur() {
    const val = form.CONSUMER_NO.trim()
    if (!val) { setConsumerNoError(''); return }
    try {
      const res = await checkConsumerNo(val, isEdit ? customer.id : null)
      setConsumerNoError(res.data.exists ? 'This consumer number already exists in the system.' : '')
    } catch {
      setConsumerNoError('')
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (consumerNoError) return
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

  const inputCls = 'w-full px-3 py-2.5 rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] dark:focus:border-emerald-500/50 focus:bg-white dark:focus:bg-white/10 transition-all'
  const readOnlyCls = 'w-full px-3 py-2.5 rounded-lg border border-gray-100 dark:border-white/5 bg-gray-100 dark:bg-white/[0.03] text-sm text-gray-400 dark:text-gray-500 cursor-not-allowed'
  const selectCls = `${inputCls} appearance-none cursor-pointer`

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
                    <div className="w-7 h-7 rounded-lg bg-white dark:bg-white/10 flex items-center justify-center shadow-sm">
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
                          {field.readOnly && <span className="ml-1 font-normal normal-case text-[10px] text-gray-400 dark:text-gray-500">(auto)</span>}
                        </label>

                        {field.type === 'select' ? (
                          <select
                            required={field.required}
                            value={form[field.key]}
                            onChange={e => set(field.key, e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select…</option>
                            {field.options.map(opt => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        ) : (
                          <>
                            <input
                              type={field.type || 'text'}
                              required={field.required}
                              readOnly={field.readOnly}
                              value={form[field.key]}
                              onChange={field.readOnly ? undefined : e => set(field.key, e.target.value)}
                              onBlur={field.key === 'CONSUMER_NO' ? handleConsumerNoBlur : undefined}
                              placeholder={field.hint || ''}
                              className={
                                field.readOnly
                                  ? readOnlyCls
                                  : field.key === 'CONSUMER_NO' && consumerNoError
                                    ? `${inputCls} border-red-400 dark:border-red-500 focus:border-red-400 dark:focus:border-red-500`
                                    : inputCls
                              }
                            />
                            {field.key === 'CONSUMER_NO' && consumerNoError && (
                              <p className="mt-1 text-xs text-red-500 dark:text-red-400">{consumerNoError}</p>
                            )}
                          </>
                        )}
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
