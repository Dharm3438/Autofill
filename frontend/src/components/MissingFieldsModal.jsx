import { useState } from 'react'
import { X, AlertTriangle, Pencil, FileWarning, Wrench, Loader2 } from 'lucide-react'

// Fields that are no longer edited on the customer form — they're filled on the
// Installation page (Manage). The installation date is derived from the Inverter
// and Solar Panel Installation checklist steps, so it can't be entered directly.
const INSTALLATION_MANAGED_KEYS = new Set(['INVERTER_SR_NO', 'PANEL_SR_NO', 'INSTALLATION_DATE'])

// Fields asked for right here in the popup rather than on the customer form.
// Deliberately NOT pre-filled from SYSTEM_COST: that's the real price and must
// not end up on the documents by clicking through.
const INLINE_FIELDS = {
  AGREEMENT_SYSTEM_COST: {
    label: 'Agreement System Cost (₹)',
    help: 'The amount printed on the Net-Metering Agreement. This is separate from the real System Cost used for payments.',
    placeholder: 'e.g. 1,20,000',
    // Whole rupees; commas are allowed while typing and removed before saving.
    validate: (v) => (/^\d+$/.test(v.replace(/[,\s]/g, '')) ? '' : 'Enter a whole rupee amount using digits (commas allowed).'),
    toValue: (v) => Number(v.replace(/[,\s]/g, '')),
  },
}

/**
 * Blocking popup shown when document generation is refused because the customer
 * is missing required template fields. The `report` is the structured payload
 * returned by the backend (HTTP 422) from /documents/generate:
 *   {
 *     message: string,
 *     missing_fields: [{ key, label, documents: [docLabel, ...] }],
 *     documents:      [{ document, missing: [{ key, label }] }],
 *   }
 */
export default function MissingFieldsModal({ customerName, report, onClose, onEdit, onSaveAndGenerate }) {
  const [values, setValues] = useState({})
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  if (!report) return null
  const missingFields = report.missing_fields || []
  const documents = report.documents || []
  const hasInstallationManaged = missingFields.some((f) => INSTALLATION_MANAGED_KEYS.has(f.key))
  const inlineFields = onSaveAndGenerate ? missingFields.filter((f) => INLINE_FIELDS[f.key]) : []
  const otherFields = missingFields.filter((f) => !inlineFields.includes(f))

  async function handleSave(e) {
    e.preventDefault()
    const data = {}
    const errs = {}
    for (const f of inlineFields) {
      const v = (values[f.key] || '').trim()
      const err = v ? INLINE_FIELDS[f.key].validate(v) : 'Required.'
      if (err) errs[f.key] = err
      else data[f.key] = INLINE_FIELDS[f.key].toValue(v)
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-[#16201b] rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
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

        <div className="p-6 space-y-5">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {report.message ||
              'Documents can’t be generated until these fields are filled in. Please complete them and try again.'}
          </p>

          {hasInstallationManaged && (
            <div className="flex items-start gap-2.5 rounded-xl border border-[#1a3a2a]/20 bg-[#1a3a2a]/5 dark:border-emerald-500/20 dark:bg-emerald-500/10 px-3 py-2.5">
              <Wrench className="w-4 h-4 mt-0.5 flex-shrink-0 text-[#1a3a2a] dark:text-emerald-400" />
              <p className="text-xs text-gray-600 dark:text-gray-300">
                Serial numbers and the installation date are entered on the{' '}
                <span className="font-semibold">Installation</span> page — open{' '}
                <span className="font-semibold">Manage</span> for this customer and fill in the
                inverter and panel serial numbers. The installation date is set automatically once
                both are entered.
              </p>
            </div>
          )}

          {/* Fields that can be filled in right here */}
          {inlineFields.length > 0 && (
            <form id="missing-inline-form" onSubmit={handleSave} className="space-y-3">
              {inlineFields.map((f) => {
                const cfg = INLINE_FIELDS[f.key]
                return (
                  <div
                    key={f.key}
                    className="rounded-xl border border-[#1a3a2a]/20 bg-[#1a3a2a]/5 dark:border-emerald-500/20 dark:bg-emerald-500/10 px-3 py-3"
                  >
                    <label htmlFor={`inline-${f.key}`} className="block text-sm font-semibold text-gray-800 dark:text-gray-100">
                      {cfg.label}
                    </label>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 mb-2">{cfg.help}</p>
                    <input
                      id={`inline-${f.key}`}
                      type="text"
                      inputMode="decimal"
                      autoFocus
                      value={values[f.key] || ''}
                      placeholder={cfg.placeholder}
                      onChange={(e) => {
                        setValues((v) => ({ ...v, [f.key]: e.target.value }))
                        setErrors((er) => ({ ...er, [f.key]: '' }))
                      }}
                      className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] dark:focus:border-emerald-500/50"
                    />
                    {errors[f.key] && (
                      <p className="mt-1 text-xs text-red-500 dark:text-red-400">{errors[f.key]}</p>
                    )}
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

          {/* Missing fields */}
          {otherFields.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
                {otherFields.length} {inlineFields.length ? 'other ' : ''}field{otherFields.length === 1 ? '' : 's'} missing
              </p>
              <div className="space-y-2">
                {otherFields.map((f) => (
                  <div
                    key={f.key}
                    className="rounded-xl border border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/10 px-3 py-2.5"
                  >
                    <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">{f.label}</p>
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
            Close
          </button>
          {onEdit && otherFields.length > 0 && (
            <button
              onClick={onEdit}
              className={
                inlineFields.length > 0
                  ? 'inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors'
                  : 'inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] transition-colors'
              }
            >
              <Pencil className="w-4 h-4" />
              Fill in Details
            </button>
          )}
          {inlineFields.length > 0 && (
            <button
              type="submit"
              form="missing-inline-form"
              disabled={saving}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] disabled:opacity-60 transition-colors"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {otherFields.length > 0 ? 'Save' : 'Save & Generate'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
