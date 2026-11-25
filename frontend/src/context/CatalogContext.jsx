import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import { getCatalog } from '../api/catalog'
import { useAuth } from './AuthContext'
import { PERM } from '../utils/access'

// Admin-managed option lists (dealers, inverter makes/capacities, panel
// companies/watts, generation meter makes). Loaded once per session and shared
// by the customer form, the installations dealer filter and the inventory
// panel, so an option an admin adds shows up everywhere at once.

const CatalogContext = createContext(null)

const READ_PERMS = [
  PERM.CUSTOMERS_CREATE, PERM.CUSTOMERS_UPDATE, PERM.INSTALLATIONS_READ, PERM.CATALOG_MANAGE,
]

export function CatalogProvider({ children }) {
  const { user, can } = useAuth()
  const allowed = Boolean(user) && can(READ_PERMS)
  const [types, setTypes] = useState([])
  const [items, setItems] = useState({})
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getCatalog()
      setTypes(res.data.data.types)
      setItems(res.data.data.items)
    } catch {
      // Leave the previous lists in place; forms still show saved values.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (allowed) refresh()
    else { setTypes([]); setItems({}) }
  }, [allowed, user?.id, refresh])

  // Swap one item in place after an admin edit (no full refetch needed).
  const upsertItem = useCallback((item) => {
    setItems((prev) => {
      const list = prev[item.type] || []
      const exists = list.some((i) => i.id === item.id)
      return {
        ...prev,
        [item.type]: exists ? list.map((i) => (i.id === item.id ? item : i)) : [...list, item],
      }
    })
  }, [])

  const value = useMemo(() => {
    // Values for a dropdown. Inactive items are hidden from new selections,
    // but `keep` (the value a record already has) is always included so an
    // old customer's deactivated dealer/make still shows when editing.
    function values(type, { includeInactive = false, keep } = {}) {
      const list = (items[type] || [])
        .filter((i) => includeInactive || i.active)
        .map((i) => i.value)
      if (keep && !list.includes(keep)) list.push(keep)
      return list
    }
    function warrantyFor(type, value) {
      return (items[type] || []).find((i) => i.value === value)?.warranty || ''
    }
    return { types, items, loading, refresh, upsertItem, values, warrantyFor }
  }, [types, items, loading, refresh, upsertItem])

  return <CatalogContext.Provider value={value}>{children}</CatalogContext.Provider>
}

export const useCatalog = () => useContext(CatalogContext)
