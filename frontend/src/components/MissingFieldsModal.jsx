import { X, AlertTriangle, Pencil, FileWarning } from 'lucide-react'

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
export default function MissingFieldsModal({ customerName, report, onClose, onEdit }) {
  if (!report) return null
  const missingFields = report.missing_fields || []
  const documents = report.documents || []

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

          {/* Missing fields */}
          {missingFields.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
                {missingFields.length} field{missingFields.length === 1 ? '' : 's'} missing
              </p>
              <div className="space-y-2">
                {missingFields.map((f) => (
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
          {onEdit && (
            <button
              onClick={onEdit}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] transition-colors"
            >
              <Pencil className="w-4 h-4" />
              Fill in Details
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
