import { useEffect, useState } from 'react'
import api from './client'

// Dealers, equipment makes (with warranty), panel watts and inverter
// capacities. The server owns these lists (backend/app/core/catalog.py) and
// rejects anything outside them, so the dropdowns are built from here.
const EMPTY = { dealers: [], inverter_makes: [], panel_makes: [], panel_watts: [], inverter_capacities: [] }

let cached = null
let pending = null

function loadCatalog() {
  if (cached) return Promise.resolve(cached)
  if (!pending) {
    pending = api.get('/catalog')
      .then((res) => { cached = res.data.data; return cached })
      .finally(() => { pending = null })
  }
  return pending
}

// The catalog, fetched once per page load. Empty lists until it arrives.
export function useCatalog() {
  const [catalog, setCatalog] = useState(cached || EMPTY)
  useEffect(() => {
    if (cached) return
    let alive = true
    loadCatalog().then((c) => { if (alive) setCatalog(c) }).catch(() => {})
    return () => { alive = false }
  }, [])
  return catalog
}
