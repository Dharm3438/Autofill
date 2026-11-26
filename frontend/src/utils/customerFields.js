import { User2, Zap, MapPin, FileText } from 'lucide-react'

// Customer form fields, shared by the customer form (CustomerModal) and the
// Missing Required Fields popup, so a field looks and saves the same in both.
//
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
export const SECTIONS = [
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

export const ALL_FIELDS = SECTIONS.flatMap((s) => s.fields.map((f) => ({ ...f, documentsOnly: s.documentsOnly })))
export const EMPTY = ALL_FIELDS.reduce((acc, f) => ({ ...acc, [f.key]: '' }), {})
export const NUMERIC = { money: true, kw: true, count: true }

// <input type="number"> attributes per kind.
export const NUMBER_INPUT = {
  money: { min: 0, step: 1, inputMode: 'numeric' },
  kw:    { min: 0, step: 'any', inputMode: 'decimal' },
  count: { min: 1, step: 1, inputMode: 'numeric' },
}

// Form strings → the typed values the API stores. Derived fields are left out.
export function toPayload(form, includeDocuments) {
  const payload = {}
  for (const f of ALL_FIELDS) {
    if (f.derived || (f.documentsOnly && !includeDocuments)) continue
    const v = String(form[f.key] ?? '').trim()
    payload[f.key] = NUMERIC[f.kind] ? (v === '' ? null : Number(v)) : v
  }
  return payload
}


// Dropdown options from the catalog. Capacity / watt items are text
// ("3.3 kW", "540") but the customer stores the number, so the option value
// is the number and the label the catalog text. Hidden items aren't offered,
// but the customer's current value always is.
export function selectOptions(field, current, catalogValues) {
  if (!NUMERIC[field.kind]) {
    return catalogValues(field.catalog, { keep: current }).map(v => ({ value: v, label: v }))
  }
  const opts = catalogValues(field.catalog).map(v => ({
    value: String(parseFloat(v)),
    label: `${v}${field.unit || ''}`,
  }))
  if (current !== '' && current != null && !opts.some(o => o.value === String(parseFloat(current)))) {
    opts.push({ value: current, label: `${current}${field.kind === 'kw' ? ' kW' : field.unit || ''}` })
  }
  return opts
}

export const FIELDS_BY_KEY = Object.fromEntries(ALL_FIELDS.map(f => [f.key, f]))
