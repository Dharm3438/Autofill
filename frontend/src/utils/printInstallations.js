// Builds a printable HTML sheet of the installation list currently shown on the
// Installations page and opens it in a new window for printing / save-as-PDF.
//
// The caller passes the already-filtered & sorted rows (exactly what the user
// sees in the UI) plus a description of the active filters, so the printout
// matches the on-screen list one-to-one.

// ₹ with Indian thousands grouping, no decimals (e.g. ₹50,000).
const fmtINR = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

// "YYYY-MM-DD" -> "DD-MM-YYYY" (project convention). Falls back to the raw
// value if it isn't in the expected shape.
function fmtDate(d) {
  if (!d) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d))
  return m ? `${m[3]}-${m[2]}-${m[1]}` : String(d)
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]))
}

// Whether a customer has the "Subsidy Received" step marked done, and when.
function subsidyCell(row) {
  const step = (row.steps || []).find((s) => s.key === 'subsidy_received')
  if (!step || step.status !== 'done') return '—'
  const date = fmtDate(step.completed_date)
  return date ? `Yes (${esc(date)})` : 'Yes'
}

// Render the dated received-payment entries as a small stacked list.
function paymentsCell(row) {
  const entries = (row.received_payments || []).filter(
    (e) => e && Number(e.amount) > 0,
  )
  if (entries.length === 0) return '<span class="muted">—</span>'
  return entries
    .map((e) => {
      const date = fmtDate(e.date)
      return `<div class="pay">${esc(fmtINR(e.amount))}${
        date ? ` <span class="muted">${esc(date)}</span>` : ''
      }</div>`
    })
    .join('')
}

/**
 * Open a print window for the given installation rows.
 * @param {Array} rows   filtered + sorted customer rows (as shown in the UI)
 * @param {Object} opts  { filters: [{label, value}], generatedAt: Date }
 */
export function printInstallations(rows, opts = {}) {
  const filters = (opts.filters || []).filter((f) => f.value)
  const generatedAt = opts.generatedAt || new Date()

  const filterLine = filters.length
    ? filters.map((f) => `${esc(f.label)}: <b>${esc(f.value)}</b>`).join(' &nbsp;·&nbsp; ')
    : 'No filters applied — showing all customers'

  const bodyRows = rows
    .map((c, i) => {
      const remaining = Number(c.remaining_payment || 0)
      return `
      <tr>
        <td class="num">${i + 1}</td>
        <td>${esc(c.CONSUMER_NO || '—')}</td>
        <td>${esc(c.CONSUMER_NAME || 'Unnamed')}</td>
        <td>${esc(c.CONSUMER_PHONE || '—')}</td>
        <td>${esc(c.DEALER_NAME || '—')}</td>
        <td class="amt">${esc(fmtINR(c.total_payment))}</td>
        <td class="payments">${paymentsCell(c)}</td>
        <td class="amt received">${esc(fmtINR(c.received_payment))}</td>
        <td class="amt ${remaining > 0 ? 'due' : 'paid'}">${
          remaining > 0 ? esc(fmtINR(remaining)) : 'Fully paid'
        }</td>
        <td class="subsidy">${subsidyCell(c)}</td>
      </tr>`
    })
    .join('')

  // Totals across the printed list.
  const totals = rows.reduce(
    (acc, c) => {
      acc.total += Number(c.total_payment || 0)
      acc.received += Number(c.received_payment || 0)
      acc.remaining += Number(c.remaining_payment || 0)
      return acc
    },
    { total: 0, received: 0, remaining: 0 },
  )

  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Installation Payment Report</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
    color: #1a2520; margin: 24px; font-size: 12px;
  }
  .head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
  h1 { font-size: 18px; margin: 0 0 4px; color: #1a3a2a; }
  .meta { font-size: 11px; color: #5a6b62; }
  .filters { margin: 10px 0 14px; padding: 8px 12px; background: #f1f5f2;
    border: 1px solid #dde7e1; border-radius: 8px; font-size: 11px; color: #33473d; }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    background: #1a3a2a; color: #fff; text-align: left; padding: 7px 8px;
    font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
  }
  tbody td { padding: 6px 8px; border-bottom: 1px solid #e4ebe7; vertical-align: top; }
  tbody tr:nth-child(even) { background: #f7faf8; }
  td.num { color: #8a988f; text-align: right; width: 28px; }
  td.amt { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  td.received { color: #1f7a4d; }
  td.due { color: #b45309; font-weight: 600; }
  td.paid { color: #1f7a4d; font-weight: 600; }
  td.payments .pay { white-space: nowrap; }
  .muted { color: #8a988f; }
  tfoot td { padding: 8px; font-weight: 700; border-top: 2px solid #1a3a2a; }
  tfoot td.amt.received { color: #1f7a4d; }
  tfoot td.amt.due { color: #b45309; }
  @media print {
    body { margin: 0; }
    thead { display: table-header-group; }
    tr { page-break-inside: avoid; }
  }
</style>
</head>
<body>
  <div class="head">
    <div>
      <h1>Installation Payment Report</h1>
      <div class="meta">${rows.length} customer${rows.length === 1 ? '' : 's'}</div>
    </div>
    <div class="meta">Generated ${esc(
      generatedAt.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }),
    )}</div>
  </div>

  <div class="filters">${filterLine}</div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Consumer No</th>
        <th>Customer Name</th>
        <th>Mobile</th>
        <th>Dealer</th>
        <th>System Cost</th>
        <th>Payments Received</th>
        <th>Total Received</th>
        <th>Remaining</th>
        <th>Subsidy</th>
      </tr>
    </thead>
    <tbody>
      ${bodyRows || '<tr><td colspan="10" style="text-align:center;color:#8a988f;padding:24px">No customers to display</td></tr>'}
    </tbody>
    ${
      rows.length
        ? `<tfoot>
      <tr>
        <td colspan="5">Total (${rows.length})</td>
        <td class="amt">${esc(fmtINR(totals.total))}</td>
        <td></td>
        <td class="amt received">${esc(fmtINR(totals.received))}</td>
        <td class="amt due">${esc(fmtINR(totals.remaining))}</td>
        <td></td>
      </tr>
    </tfoot>`
        : ''
    }
  </table>

  <script>
    window.onload = function () {
      window.focus();
      window.print();
    };
  </script>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) return false // popup blocked
  win.document.open()
  win.document.write(html)
  win.document.close()
  return true
}
