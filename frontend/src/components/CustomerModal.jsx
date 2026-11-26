import { useState, useEffect } from 'react'
import { X, User2, Zap, MapPin, UserPlus, Pencil, FileText } from 'lucide-react'
import { createCustomer, updateCustomer, checkConsumerNo } from '../api/customers'
import { useCatalog } from '../context/CatalogContext'
import { useAuth } from '../context/AuthContext'
import { PERM } from '../utils/access'
import toast from 'react-hot-toast'

// Field `kind`s and how the form value is sent to the API:
//   (none)  text, sent as typed ('' clears it)
//   money   whole rupees            → integer
//   kw      kilowatts               → number
//   count   whole number            → integer
//   date    <input type="date">     → "YYYY-MM-DD"
// Select fields take their options from the admin-managed catalog
// (`catalog: <list type>`); admins add new dealers / equipment from the
// Customers page ("Dealers & Equipment"). `derived` fields are calculated by
// the server on save; the form only shows a preview and never sends them.
const SECTIONS = [
  {
    title: 'Consumer Information',
    icon: User2,
    color: 'text-blue-600',
    bg: 'bg-blue-50',
    fields: [
      { key: 'CONSUMER_NAME',    label: 'Consumer Name',    required: true },
      { key: 'CONSUMER_ADDRESS', label: 'Address',          required: true, span: 2 },
      { key: 'CONSUMER_PHONE',   label: 'Phone',            required: true, type: 'tel', hint: '10-digit mobile number' },
      { key: 'CONSUMER_EMAIL',   label: 'Email',            type: 'email' },
      { key: 'CONSUMER_AADHAR',  label: 'Aadhaar Number',   required: true, hint: '12 digits' },
      { key: 'CONSUMER_NO',      label: 'Consumer No',      required: true },
      { key: 'DEALER_NAME',      label: 'Dealer Name',      required: true, type: 'select', catalog: 'dealer' },
      { key: 'CONSUMER_APP_NO',     label: 'Application No' },
      { key: 'CONSUMER_APP_DATE',   label: 'Application Date', kind: 'date' },
      { key: 'SUBSIDY_APP_NO',      label: 'Subsidy Portal Application No' },
      { key: 'SUBSIDY_APP_DATE',    label: 'Subsidy Portal Application Date', kind: 'date' },
      { key: 'SANCTIONED_CAPACITY', label: 'Sanctioned Capacity (kW)', kind: 'kw' },
    ],
  },
  {
    title: 'Solar System',
    icon: Zap,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    fields: [
      { key: 'SOLAR_CAPACITY', label: 'Solar Capacity (kW)', kind: 'kw', required: true },
      { key: 'INVERTER_MAKE', label: 'Inverter Make', type: 'select', required: true, catalog: 'inverter_make' },
      {
        key: 'INVERTER_CAPACITY', label: 'Inverter Capacity', type: 'select', kind: 'kw', required: true,
        catalog: 'inverter_capacity',
      },
      { key: 'INVERTER_GUARANTEE', label: 'Inverter Guarantee', derived: true },
      { key: 'INVERTER_SR_NO', label: 'Inverter Serial No', hint: 'Optional · comma-separated if more than one' },
      { key: 'PANEL_COMPANY', label: 'Panel Company', type: 'select', required: true, catalog: 'panel_company' },
      {
        key: 'PANEL_WATT', label: 'Panel Watt', type: 'select', kind: 'count', required: true,
        catalog: 'panel_watt', unit: ' W',
      },
      { key: 'NO_OF_PANEL',          label: 'No of Panels', kind: 'count', required: true },
      { key: 'TOTAL_PANEL_CAPACITY', label: 'Total Panel Capacity (W)', derived: true },
      { key: 'PANEL_GUARANTEE',      label: 'Panel Guarantee', derived: true },
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
      { key: 'SYSTEM_COST',              label: 'System Cost (₹)', kind: 'money', required: true },
    ],
  },
  {
    // Document users only (the backend also hides and ignores these fields for
    // other roles). Shown on edit, not create — the agreement cost is normally
    // asked for in the Missing Required Fields popup when generating documents.
    title: 'Documents',
    icon: FileText,
    color: 'text-sky-600',
    bg: 'bg-sky-50',
    documentsOnly: true,
    fields: [
      {
        key: 'AGREEMENT_SYSTEM_COST',
        label: 'Agreement System Cost (₹)',
        kind: 'money',
        hint: 'Printed on the Net-Metering Agreement',
      },
    ],
  },
]

const ALL_FIELDS = SECTIONS.flatMap((s) => s.fields.map((f) => ({ ...f, documentsOnly: s.documentsOnly })))
const EMPTY = ALL_FIELDS.reduce((acc, f) => ({ ...acc, [f.key]: '' }), {})
const NUMERIC = { money: true, kw: true, count: true }

// <input type="number"> attributes per kind.
const NUMBER_INPUT = {
  money: { min: 0, step: 1, inputMode: 'numeric' },
  kw:    { min: 0, step: 'any', inputMode: 'decimal' },
  count: { min: 1, step: 1, inputMode: 'numeric' },
}

// Form strings → the typed values the API stores. Derived fields are left out.
function toPayload(form, includeDocuments) {
  const payload = {}
  for (const f of ALL_FIELDS) {
    if (f.derived || (f.documentsOnly && !includeDocuments)) continue
    const v = String(form[f.key] ?? '').trim()
    payload[f.key] = NUMERIC[f.kind] ? (v === '' ? null : Number(v)) : v
  }
  return payload
}

export default function CustomerModal({ customer, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(false)
  const [consumerNoError, setConsumerNoError] = useState('')
  const isEdit = Boolean(customer)
  const { can } = useAuth()
  const { values: catalogValues, warrantyFor } = useCatalog()
  const showDocuments = isEdit && can(PERM.DOCUMENTS_MANAGE)
  const sections = SECTIONS.filter(s => !s.documentsOnly || showDocuments)

  useEffect(() => {
    if (customer) {
      const filled = { ...EMPTY }
      Object.keys(EMPTY).forEach(k => { filled[k] = customer[k] == null ? '' : String(customer[k]) })
      setForm(filled)
    }
  }, [customer])

  function set(key, val) {
    setForm(f => ({ ...f, [key]: val }))
  }

  // Dropdown options from the catalog. Capacity / watt items are text
  // ("3.3 kW", "540") but the customer stores the number, so the option value
  // is the number and the label the catalog text. Hidden items aren't offered,
  // but the customer's current value always is.
  function selectOptions(field) {
    const current = form[field.key]
    if (!NUMERIC[field.kind]) {
      return catalogValues(field.catalog, { keep: current }).map(v => ({ value: v, label: v }))
    }
    const opts = catalogValues(field.catalog).map(v => ({
      value: String(parseFloat(v)),
      label: `${v}${field.unit || ''}`,
    }))
    if (current !== '' && !opts.some(o => o.value === String(parseFloat(current)))) {
      opts.push({ value: current, label: `${current}${field.kind === 'kw' ? ' kW' : field.unit || ''}` })
    }
    return opts
  }

  // Preview of what the server will calculate on save.
  function derivedPreview(key) {
    if (key === 'INVERTER_GUARANTEE') return warrantyFor('inverter_make', form.INVERTER_MAKE)
    if (key === 'PANEL_GUARANTEE') return warrantyFor('panel_company', form.PANEL_COMPANY)
    if (key === 'TOTAL_PANEL_CAPACITY') {
      const w = parseInt(form.PANEL_WATT, 10)
      const q = parseInt(form.NO_OF_PANEL, 10)
      return w > 0 && q > 0 ? String(w * q) : ''
    }
    return ''
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
    // Only send document fields when they're on screen, so other roles never
    // submit them (a blank value would otherwise mean "clear it").
    const payload = toPayload(form, showDocuments)
    try {
      let res
      if (isEdit) {
        res = await updateCustomer(customer.id, payload)
        toast.success('Customer updated')
      } else {
        res = await createCustomer(payload)
        toast.success('Customer added')
      }
      // The saved customer, so the list can update that row without refetching.
      onSaved(res.data?.data)
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
            {sections.map(section => {
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
                          {field.derived && <span className="ml-1 font-normal normal-case text-[10px] text-gray-400 dark:text-gray-500">(auto)</span>}
                        </label>

                        {field.type === 'select' ? (
                          <select
                            required={field.required}
                            value={form[field.key]}
                            onChange={e => set(field.key, e.target.value)}
                            className={selectCls}
                          >
                            <option value="">Select…</option>
                            {/* Hidden (deactivated) options aren't offered, but the
                                value this customer already has always is. */}
                            {selectOptions(field).map(o => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                        ) : (
                          <>
                            <input
                              type={field.kind === 'date' ? 'date' : NUMERIC[field.kind] ? 'number' : field.type || 'text'}
                              {...(NUMBER_INPUT[field.kind] || {})}
                              required={field.required}
                              readOnly={field.derived}
                              value={field.derived ? derivedPreview(field.key) : form[field.key]}
                              onChange={field.derived ? undefined : e => set(field.key, e.target.value)}
                              onBlur={field.key === 'CONSUMER_NO' ? handleConsumerNoBlur : undefined}
                              placeholder={field.hint || ''}
                              className={
                                field.derived
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
