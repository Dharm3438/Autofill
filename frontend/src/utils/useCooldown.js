import { useEffect, useState } from 'react'

// Seconds left before "Resend code" is allowed again (the server enforces 60s).
export function useCooldown(seconds = 60) {
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (left <= 0) return undefined
    const t = setTimeout(() => setLeft((s) => s - 1), 1000)
    return () => clearTimeout(t)
  }, [left])
  return [left, () => setLeft(seconds)]
}
