import { useState } from 'react'
import { X, AlertTriangle, FileWarning, Info, Loader2, Sparkles } from 'lucide-react'
import { useCatalog } from '../context/CatalogContext'
import { FIELDS_BY_KEY, NUMERIC, NUMBER_INPUT, selectOptions } from '../utils/customerFields'

// Extra help shown under specific inputs.
const FIELD_HELP = {
  // Deliberately NOT pre-filled from SYSTEM_COST: that's the real price and
  // must not end up on the documents by clicking through.
  AGREEMENT_SYSTEM_COST:
    'The amount printed on the Net-Metering Agreement. This is separate from the real System Cost used for payments.',
}

// Fields the server works out itself, so they can't be typed in here. Each
// says what to fill in (or where) so the server can calculate it.
const DERIVED_HELP = {
  TOTAL_PANEL_CAPACITY: 'Calculated automatically from Panel Watt × No of Panels.',
  INVERTER_GUARANTEE:
    'Taken from the Inverter Make’s warranty. Pick an Inverter Make, or ask an admin to set its warranty in Dealers & Equipment.',
  PANEL_GUARANTEE:
    'Taken from the Panel Company’s warranty. Pick a Panel Company, or ask an admin to set its warranty in Dealers & Equipment.',
  INSTALLATION_DATE:
    'Set automatically from the Inverter / Solar Panel Installation checklist steps on the Installations page (open Manage for this customer).',
}

// A missing field can be filled in right here when it's a normal (not
// server-calculated) customer form field.
function editableField(key) {
  const f = FIELDS_BY_KEY[key]
  return f && !f.derived ? f : null
}

/**
 * Blocking popup shown when document generation is refused because the customer
 * is missing required template fields. Every missing customer field gets an
 * input right here; "Save & Generate" stores the values on the customer (the
 * same fields as the customer form, so they show up everywhere) and retries
 * generation.
 *
 * The `report` is the structured payload returned by the backend (HTTP 422)
 * from /documents/generate:
 *   {
 *     message: string,
 *     missing_fields: [{ key, label, documents: [docLabel, ...] }],
 *     documents:      [{ document, missing: [{ key, label }] }],
 *   }
 */
export default function MissingFieldsModal({ customerName, report, onClose, onSaveAndGenerate }) {
  const [values, setValues] = useState({})
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const { values: catalogValues } = useCatalog()

  if (!report) return null
  const missingFields = report.missing_fields || []
  const documents = report.documents || []
  const canSave = Boolean(onSaveAndGenerate)
  const inlineFields = canSave ? missingFields.filter((f) => editableField(f.key)) : []
  const otherFields = missingFields.filter((f) => !inlineFields.includes(f))
  // Derived fields that will be calculated once the inputs above are saved
  // (e.g. Total Panel Capacity from Panel Watt + No of Panels) don't block.
  const blockingOther = otherFields.filter(
    (f) => !(f.key === 'TOTAL_PANEL_CAPACITY' && inlineFields.some((i) => i.key === 'PANEL_WATT' || i.key === 'NO_OF_PANEL')),
  )

  function setValue(key, v) {
    setValues((prev) => ({ ...prev, [key]: v }))
    setErrors((prev) => ({ ...prev, [key]: '' }))
  }

  async function handleSave(e) {
    e.preventDefault()
    const data = {}
    const errs = {}
    for (const { key } of inlineFields) {
      const field = editableField(key)
      const v = String(values[key] ?? '').trim()
      if (!v) {
        errs[key] = 'Required.'
      } else if (NUMERIC[field.kind]) {
        const n = Number(v)
        if (!Number.isFinite(n) || n < 0) errs[key] = 'Enter a valid number.'
        else data[key] = n
      } else {
        data[key] = v
      }
    }
    setErrors(errs)
    if (Object.keys(errs).length) return
    setSaving(true)
    try {
      await onSaveAndGenerate(data)
    } finally {
      setSaving(false)
    }
  }

  const inputCls =
    'w-full px-3 py-2 rounded-lg border bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] dark:focus:border-emerald-500/50'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-[#16201b] rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-gray-100 dark:border-white/10">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Missing Required Fields</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{customerName}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {inlineFields.length > 0
              ? 'Fill in the missing details below. They’re saved to the customer, then the documents are generated.'
              : report.message || 'Documents can’t be generated until these fields are filled in.'}
          </p>

          {/* Fields that can be filled in right here */}
          {inlineFields.length > 0 && (
            <form id="missing-inline-form" onSubmit={handleSave} noValidate className="space-y-3">
              {inlineFields.map((f, i) => {
                const field = editableField(f.key)
                const id = `missing-${f.key}`
                const err = errors[f.key]
                const cls = `${inputCls} ${err ? 'border-red-400 dark:border-red-500' : 'border-gray-200 dark:border-white/10'}`
                const value = values[f.key] ?? ''
                return (
                  <div
                    key={f.key}
                    className="rounded-xl border border-[#1a3a2a]/20 bg-[#1a3a2a]/5 dark:border-emerald-500/20 dark:bg-emerald-500/10 px-3 py-3"
                  >
                    <label htmlFor={id} className="block text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1.5">
                      {field.label}
                    </label>
                    {FIELD_HELP[f.key] && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 -mt-0.5 mb-2">{FIELD_HELP[f.key]}</p>
                    )}
                    {field.type === 'select' ? (
                      <select
                        id={id}
                        autoFocus={i === 0}
                        value={value}
                        onChange={(e) => setValue(f.key, e.target.value)}
                        className={`${cls} appearance-none cursor-pointer`}
                      >
                        <option value="">Select…</option>
                        {selectOptions(field, value, catalogValues).map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={id}
                        autoFocus={i === 0}
                        type={field.kind === 'date' ? 'date' : NUMERIC[field.kind] ? 'number' : field.type || 'text'}
                        {...(NUMBER_INPUT[field.kind] || {})}
                        value={value}
                        placeholder={FIELD_HELP[f.key] ? '' : field.hint || ''}
                        onChange={(e) => setValue(f.key, e.target.value)}
                        className={cls}
                      />
                    )}
                    {err && <p className="mt-1 text-xs text-red-500 dark:text-red-400">{err}</p>}
                    {f.documents?.length > 0 && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
                        Needed in: {f.documents.join(', ')}
                      </p>
                    )}
                  </div>
                )
              })}
            </form>
          )}

          {/* Missing fields that can't be typed in here */}
          {otherFields.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
                {inlineFields.length ? 'Also missing' : `${otherFields.length} field${otherFields.length === 1 ? '' : 's'} missing`}
              </p>
              <div className="space-y-2">
                {otherFields.map((f) => (
                  <div
                    key={f.key}
                    className="rounded-xl border border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10 px-3 py-2.5"
                  >
                    <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">{f.label}</p>
                    {DERIVED_HELP[f.key] && (
                      <p className="flex items-start gap-1.5 text-xs text-gray-600 dark:text-gray-300 mt-1">
                        <Info className="w-3.5 h-3.5 mt-px flex-shrink-0" />
                        {DERIVED_HELP[f.key]}
                      </p>
                    )}
                    {f.documents?.length > 0 && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        Needed in: {f.documents.join(', ')}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Per-document breakdown */}
          {documents.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
                Documents blocked
              </p>
              <div className="space-y-2">
                {documents.map((d) => (
                  <div
                    key={d.document}
                    className="rounded-xl border border-gray-200 bg-gray-50/60 dark:border-white/10 dark:bg-white/5 px-3 py-2.5"
                  >
                    <div className="flex items-center gap-2">
                      <FileWarning className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                      <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">{d.document}</p>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 pl-6">
                      {(d.missing || []).map((m) => m.label).join(', ')}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-100 dark:border-white/10">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          >
            {inlineFields.length > 0 ? 'Cancel' : 'Close'}
          </button>
          {inlineFields.length > 0 && (
            <button
              type="submit"
              form="missing-inline-form"
              disabled={saving}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-60 transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {blockingOther.length > 0 ? 'Save Details' : 'Save & Generate'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
