// Display helpers for the typed values the API returns (numbers and
// "YYYY-MM-DD" dates). Blank (null/undefined/'') shows as ''.

const blank = (v) => v === null || v === undefined || v === ''

// ₹ with Indian grouping: 150000 -> "₹1,50,000"
export const fmtINR = (n) =>
  blank(n) ? '' : `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

// 5 -> "5 kW", 3.3 -> "3.3 kW"
export const fmtKw = (n) => (blank(n) ? '' : `${Number(n)} kW`)

// "2026-03-05" -> "05-03-2026"
export const fmtDate = (iso) => {
  if (blank(iso)) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso))
  return m ? `${m[3]}-${m[2]}-${m[1]}` : String(iso)
}

// 10 -> "10 years"
export const fmtYears = (n) => (blank(n) ? '' : `${n} ${Number(n) === 1 ? 'year' : 'years'}`)
