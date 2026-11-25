import { useState } from 'react'
import { X, ListPlus, Plus, Eye, EyeOff, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { addCatalogItem, updateCatalogItem } from '../api/catalog'
import { useCatalog } from '../context/CatalogContext'

// Admin screen for the customer-form option lists. Items can be added, have
// their warranty changed, or be hidden — never renamed or deleted, because
// customers store the text itself and an old record must keep its value.

const PLACEHOLDERS = {
  dealer: 'Dealer name',
  inverter_make: 'Inverter make, e.g. Luminous',
  inverter_capacity: 'Capacity, e.g. 7 or 3.3',
  panel_company: 'Panel company, e.g. Vikram',
  panel_watt: 'Watt, e.g. 550',
}

const HELP = {
  kw: 'Saved as “7 kW”. ',
  watt: 'Numbers only — shown as “550 W”. ',
}

export default function CatalogModal({ onClose }) {
  const { types, items, loading, upsertItem } = useCatalog()
  const [tab, setTab] = useState('dealer')
  const [value, setValue] = useState('')
  const [warranty, setWarranty] = useState('')
  const [adding, setAdding] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [warrantyDrafts, setWarrantyDrafts] = useState({})

  const type = types.find((t) => t.key === tab) || { key: tab, label: '', format: 'text', has_warranty: false }
  const list = items[tab] || []
  const active = list.filter((i) => i.active)
  const hidden = list.filter((i) => !i.active)
  const unit = type.format === 'watt' ? ' W' : ''

  function switchTab(key) {
    setTab(key)
    setValue('')
    setWarranty('')
  }

  async function submit(e) {
    e.preventDefault()
    if (!value.trim()) return
    if (type.has_warranty && !warranty.trim()) {
      toast.error('Enter the warranty in years')
      return
    }
    setAdding(true)
    try {
      const res = await addCatalogItem({
        type: tab,
        value,
        ...(type.has_warranty ? { warranty } : {}),
      })
      upsertItem(res.data.data)
      toast.success(`Added ${res.data.data.value}${unit}`)
      setValue('')
      setWarranty('')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not add')
    } finally {
      setAdding(false)
    }
  }

  async function update(item, body, okMsg) {
    setBusyId(item.id)
    try {
      const res = await updateCatalogItem(item.id, body)
      upsertItem(res.data.data)
      if (okMsg) toast.success(okMsg)
      return true
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save')
      return false
    } finally {
      setBusyId(null)
    }
  }

  async function saveWarranty(item) {
    const draft = warrantyDrafts[item.id]
    if (draft === undefined) return
    const clear = () => setWarrantyDrafts((d) => {
      const next = { ...d }
      delete next[item.id]
      return next
    })
    if (draft.trim() === '' || draft === item.warranty) { clear(); return }
    if (await update(item, { warranty: draft }, `${item.value} warranty updated`)) clear()
  }

  const inputCls = 'w-full px-3 py-2.5 rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25 dark:focus:ring-emerald-500/30 focus:border-[#1a3a2a] dark:focus:border-emerald-500/50 focus:bg-white dark:focus:bg-white/10 transition-all'

  function renderRow(item) {
    const busy = busyId === item.id
    return (
      <li key={item.id} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg ${item.active ? 'bg-gray-50 dark:bg-white/[0.03]' : 'bg-gray-50/50 dark:bg-white/[0.015]'}`}>
        <span className={`flex-1 min-w-0 truncate text-sm ${item.active ? 'text-gray-800 dark:text-gray-100 font-medium' : 'text-gray-400 dark:text-gray-500 line-through'}`}>
          {item.value}{unit}
        </span>
        {type.has_warranty && (
          <input
            value={warrantyDrafts[item.id] ?? item.warranty}
            onChange={(e) => setWarrantyDrafts((d) => ({ ...d, [item.id]: e.target.value }))}
            onBlur={() => saveWarranty(item)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            disabled={busy}
            aria-label={`Warranty for ${item.value}`}
            title="Warranty — auto-fills the guarantee on new customers"
            className="w-24 px-2 py-1 text-xs text-center rounded-md border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#1a3a2a]/25"
          />
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() => update(
            item,
            { active: !item.active },
            item.active ? `${item.value} hidden from new customers` : `${item.value} is back in the list`,
          )}
          className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold rounded-md border transition-colors disabled:opacity-50 flex-shrink-0 ${
            item.active
              ? 'border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'
              : 'border-emerald-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10'
          }`}
        >
          {busy
            ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            : item.active ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          {item.active ? 'Hide' : 'Show'}
        </button>
      </li>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 backdrop-blur-sm overflow-y-auto py-6 px-4">
      <div className="bg-white dark:bg-[#16201b] rounded-2xl shadow-2xl w-full max-w-2xl ring-1 ring-black/10 dark:ring-white/10 my-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 bg-[#1a3a2a] rounded-t-2xl">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center flex-shrink-0">
              <ListPlus className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="font-semibold text-white text-base leading-tight">Dealers &amp; Equipment</h2>
              <p className="text-white/60 text-xs mt-0.5">Options offered in the customer form and inventory</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-colors" aria-label="Close">
            <X className="w-4 h-4 text-white" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-4 pt-4 overflow-x-auto border-b border-gray-100 dark:border-white/10">
          {types.map((t) => (
            <button
              key={t.key}
              onClick={() => switchTab(t.key)}
              className={`px-3 py-2 text-xs font-semibold whitespace-nowrap rounded-t-lg border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-[#1a3a2a] dark:border-emerald-400 text-[#1a3a2a] dark:text-emerald-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              {t.label}
              <span className="ml-1.5 text-[10px] font-normal text-gray-400 dark:text-gray-500">
                {(items[t.key] || []).filter((i) => i.active).length}
              </span>
            </button>
          ))}
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Add */}
          <form onSubmit={submit} className="space-y-1.5">
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={PLACEHOLDERS[tab] || 'New option'}
                className={inputCls}
                autoFocus
              />
              {type.has_warranty && (
                <input
                  value={warranty}
                  onChange={(e) => setWarranty(e.target.value)}
                  placeholder="Warranty (years)"
                  className={`${inputCls} sm:w-40`}
                />
              )}
              <button
                type="submit"
                disabled={adding || !value.trim()}
                className="inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-[#1a3a2a] text-white text-sm font-semibold rounded-lg hover:bg-[#2d5a3d] disabled:opacity-50 transition-colors flex-shrink-0"
              >
                <Plus className="w-4 h-4" /> Add
              </button>
            </div>
            <p className="text-[11px] text-gray-400 dark:text-gray-500">
              {HELP[type.format] || ''}
              {type.has_warranty && 'The warranty auto-fills the guarantee when this make is picked. '}
              Options can’t be renamed or deleted: customers keep the exact text. Hide an option to stop offering it.
            </p>
          </form>

          {/* List */}
          {loading && list.length === 0 ? (
            <div className="flex justify-center py-10">
              <RefreshCw className="w-5 h-5 text-[#1a3a2a] dark:text-emerald-400 animate-spin" />
            </div>
          ) : (
            <div className="max-h-[50vh] overflow-y-auto space-y-4 pr-1">
              {active.length === 0 ? (
                <p className="text-sm text-gray-400 dark:text-gray-500 py-4 text-center">Nothing in this list yet</p>
              ) : (
                <ul className="space-y-1.5">
                  {active.map(renderRow)}
                </ul>
              )}
              {hidden.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1.5">
                    Hidden — not offered for new customers
                  </p>
                  <ul className="space-y-1.5">
                    {hidden.map(renderRow)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
