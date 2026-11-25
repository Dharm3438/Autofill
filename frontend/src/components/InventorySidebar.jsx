import { useState, useEffect, useCallback } from 'react'
import {
  Boxes, Pencil, Check, Plus, X, AlertTriangle, RefreshCw, PackageX,
} from 'lucide-react'
import { getInventoryOverview, setInventoryStock } from '../api/inventory'
import { useCatalog } from '../api/catalog'
import toast from 'react-hot-toast'

const rowKey = (r) => `${r.category}|${r.company}|${r.spec}`

// Which selectors the "add stock" form shows for each category. Specs are the
// plain numbers as text ("540", "3.3") — the same text the server uses for a
// customer's panel watt / inverter capacity, so stock lines match demand.
function addFields(catalog) {
  return {
    panel: {
      company: { label: 'Company', options: catalog.panel_makes.map((m) => m.name) },
      spec: { label: 'Watt', options: catalog.panel_watts.map(String), suffix: ' W' },
    },
    inverter: {
      company: { label: 'Make', options: catalog.inverter_makes.map((m) => m.name) },
      spec: { label: 'Capacity', options: catalog.inverter_capacities.map(String), suffix: ' kW' },
    },
    generation_meter: {
      company: { label: 'Make', options: null }, // free text
    },
  }
}

// Ensure the single generic Net Meter line always exists so it can be stocked
// even before any customer demand has been entered.
function withNetMeterPlaceholder(categories) {
  return categories.map((cat) => {
    if (cat.key !== 'net_meter' || cat.items.length > 0) return cat
    return {
      ...cat,
      items: [{
        category: 'net_meter', company: '', spec: '', label: 'Net Meter',
        required: 0, consumed: 0, base_stock: 0, in_stock: 0, shortfall: 0,
      }],
    }
  })
}

export default function InventorySidebar({ refreshSignal }) {
  const ADD_FIELDS = addFields(useCatalog())
  const [categories, setCategories] = useState([])
  const [totals, setTotals] = useState({})
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [drafts, setDrafts] = useState({})   // rowKey -> string (base_stock while editing)
  const [savingKey, setSavingKey] = useState(null)
  const [addFor, setAddFor] = useState(null)  // category key with an open add form
  const [addForm, setAddForm] = useState({ company: '', spec: '', stock: '' })

  const fetchData = useCallback(async () => {
    try {
      const res = await getInventoryOverview()
      setCategories(withNetMeterPlaceholder(res.data.data.categories))
      setTotals(res.data.data.totals)
    } catch {
      toast.error('Failed to load inventory')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load + refetch whenever the parent signals a change (e.g. a step was
  // marked done, which shifts a unit from required to consumed).
  useEffect(() => {
    fetchData()
  }, [refreshSignal, fetchData])

  function startEditing() {
    const seed = {}
    categories.forEach((cat) =>
      cat.items.forEach((r) => { seed[rowKey(r)] = String(r.base_stock) }),
    )
    setDrafts(seed)
    setEditMode(true)
  }

  function stopEditing() {
    setEditMode(false)
    setAddFor(null)
    setDrafts({})
  }

  async function saveStock({ category, company, spec }, value) {
    const stock = parseInt(value, 10)
    if (isNaN(stock) || stock < 0) return
    const key = `${category}|${company}|${spec}`
    setSavingKey(key)
    try {
      await setInventoryStock({ category, company, spec, stock })
      await fetchData()
    } catch {
      toast.error('Could not save stock')
    } finally {
      setSavingKey(null)
    }
  }

  function onDraftBlur(r) {
    const key = rowKey(r)
    const val = drafts[key]
    if (val === undefined || val === String(r.base_stock)) return
    saveStock(r, val)
  }

  async function submitAdd(catKey) {
    const fields = ADD_FIELDS[catKey]
    const company = (addForm.company || '').trim()
    const spec = (addForm.spec || '').trim()
    if (fields?.company && !company) {
      toast.error(`Select a ${fields.company.label.toLowerCase()}`)
      return
    }
    const stock = parseInt(addForm.stock, 10)
    if (isNaN(stock) || stock < 0) {
      toast.error('Enter a valid quantity')
      return
    }
    await saveStock({ category: catKey, company, spec }, stock)
    setAddForm({ company: '', spec: '', stock: '' })
    setAddFor(null)
  }

  return (
    <div className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-4 border-b border-gray-100 dark:border-white/10">
        <div className="w-9 h-9 rounded-xl bg-[#1a3a2a] flex items-center justify-center flex-shrink-0">
          <Boxes className="w-4.5 h-4.5 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-bold text-gray-900 dark:text-gray-100 leading-tight">Inventory</h2>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">Required vs. in stock</p>
        </div>
        {editMode ? (
          <button
            onClick={stopEditing}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] transition-colors"
          >
            <Check className="w-3.5 h-3.5" /> Done
          </button>
        ) : (
          <button
            onClick={startEditing}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors disabled:opacity-50"
          >
            <Pencil className="w-3.5 h-3.5" /> Edit stock
          </button>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-2 text-[11px] text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-white/10">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-400" /> Need (pending)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500" /> In stock
        </span>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-2">
          <RefreshCw className="w-5 h-5 text-[#1a3a2a] dark:text-emerald-400 animate-spin" />
          <p className="text-xs text-gray-400 dark:text-gray-500">Loading inventory…</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-100 dark:divide-white/10 max-h-[calc(100vh-13rem)] overflow-y-auto">
          {categories.map((cat) => {
            const t = totals[cat.key] || {}
            const canAdd = !!ADD_FIELDS[cat.key]
            return (
              <div key={cat.key} className="px-4 py-3">
                {/* Category header */}
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    {cat.label}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-amber-600 dark:text-amber-400 font-semibold">
                      {t.required || 0} need
                    </span>
                    <span className="text-gray-300 dark:text-gray-600">·</span>
                    <span className={`font-semibold ${(t.in_stock || 0) < 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                      {t.in_stock || 0} in stock
                    </span>
                  </div>
                </div>

                {/* Rows */}
                {cat.items.length === 0 && !(editMode && canAdd) ? (
                  <div className="flex items-center gap-2 py-2 text-xs text-gray-400 dark:text-gray-500">
                    <PackageX className="w-3.5 h-3.5" /> Nothing tracked yet
                  </div>
                ) : (
                  <ul className="space-y-1.5">
                    {cat.items.map((r) => {
                      const key = rowKey(r)
                      const short = r.shortfall > 0
                      return (
                        <li
                          key={key}
                          className={`flex items-center gap-2 px-2.5 py-2 rounded-lg ${
                            short
                              ? 'bg-red-50 dark:bg-red-500/10'
                              : 'bg-gray-50 dark:bg-white/[0.03]'
                          }`}
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate">
                              {r.label}
                            </p>
                            <p className="text-[10px] text-gray-400 dark:text-gray-500">
                              {r.base_stock} stocked · {r.consumed} used
                              {short && (
                                <span className="text-red-500 dark:text-red-400 font-semibold">
                                  {' '}· short {r.shortfall}
                                </span>
                              )}
                            </p>
                          </div>

                          {/* Need */}
                          <div className="text-center w-12 flex-shrink-0">
                            <p className="text-sm font-bold text-amber-600 dark:text-amber-400 leading-none">
                              {r.required}
                            </p>
                            <p className="text-[9px] text-gray-400 dark:text-gray-500 mt-0.5">need</p>
                          </div>

                          {/* In stock — editable in edit mode */}
                          {editMode ? (
                            <div className="w-16 flex-shrink-0 relative">
                              <input
                                type="number"
                                min="0"
                                value={drafts[key] ?? ''}
                                onChange={(e) =>
                                  setDrafts((d) => ({ ...d, [key]: e.target.value }))
                                }
                                onBlur={() => onDraftBlur(r)}
                                onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
                                className="w-full px-2 py-1 text-sm text-center font-semibold rounded-md border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25"
                                aria-label={`Stock for ${r.label}`}
                              />
                              {savingKey === key && (
                                <RefreshCw className="w-3 h-3 text-emerald-500 animate-spin absolute -right-4 top-1/2 -translate-y-1/2" />
                              )}
                            </div>
                          ) : (
                            <div className="text-center w-12 flex-shrink-0">
                              <p className={`text-sm font-bold leading-none ${
                                r.in_stock < 0
                                  ? 'text-red-600 dark:text-red-400'
                                  : short
                                    ? 'text-amber-600 dark:text-amber-400'
                                    : 'text-emerald-600 dark:text-emerald-400'
                              }`}>
                                {r.in_stock}
                              </p>
                              <p className="text-[9px] text-gray-400 dark:text-gray-500 mt-0.5">have</p>
                            </div>
                          )}

                          {short && !editMode && (
                            <AlertTriangle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" title={`Short ${r.shortfall}`} />
                          )}
                        </li>
                      )
                    })}
                  </ul>
                )}

                {/* Add stock (edit mode only) */}
                {editMode && canAdd && (
                  <div className="mt-2">
                    {addFor === cat.key ? (
                      <AddStockForm
                        catKey={cat.key}
                        form={addForm}
                        setForm={setAddForm}
                        onSubmit={() => submitAdd(cat.key)}
                        onCancel={() => { setAddFor(null); setAddForm({ company: '', spec: '', stock: '' }) }}
                      />
                    ) : (
                      <button
                        onClick={() => { setAddFor(cat.key); setAddForm({ company: '', spec: '', stock: '' }) }}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#1a3a2a] dark:text-emerald-400 hover:underline"
                      >
                        <Plus className="w-3 h-3" /> Add stock item
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function AddStockForm({ catKey, form, setForm, onSubmit, onCancel }) {
  const fields = addFields(useCatalog())[catKey]
  const selCls = 'flex-1 min-w-0 px-2 py-1.5 text-xs rounded-md border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25'
  return (
    <div className="p-2.5 rounded-lg border border-dashed border-gray-300 dark:border-white/15 bg-gray-50 dark:bg-white/[0.03] space-y-2">
      <div className="flex gap-2">
        {fields.company && (
          fields.company.options ? (
            <select
              value={form.company}
              onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))}
              className={selCls}
            >
              <option value="">{fields.company.label}…</option>
              {fields.company.options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input
              type="text"
              placeholder={fields.company.label}
              value={form.company}
              onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))}
              className={selCls}
            />
          )
        )}
        {fields.spec && (
          <select
            value={form.spec}
            onChange={(e) => setForm((f) => ({ ...f, spec: e.target.value }))}
            className={selCls}
          >
            <option value="">{fields.spec.label}…</option>
            {fields.spec.options.map((o) => (
              <option key={o} value={o}>{o}{fields.spec.suffix || ''}</option>
            ))}
          </select>
        )}
      </div>
      <div className="flex gap-2">
        <input
          type="number"
          min="0"
          placeholder="Qty in stock"
          value={form.stock}
          onChange={(e) => setForm((f) => ({ ...f, stock: e.target.value }))}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          className={selCls}
        />
        <button
          onClick={onSubmit}
          className="px-3 py-1.5 text-xs font-semibold rounded-md bg-[#1a3a2a] text-white hover:bg-[#2d5a3d] transition-colors flex-shrink-0"
        >
          Add
        </button>
        <button
          onClick={onCancel}
          className="p-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 flex-shrink-0"
          aria-label="Cancel"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
