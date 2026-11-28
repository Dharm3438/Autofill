// Documents come straight from Cloudflare R2, not through the API server.
//
// Render bills every byte the server sends out; R2 downloads are free. So the
// server only hands out short-lived links (it still decides who may see what),
// and the browser fetches the files, puts the stamped first page in front of
// the NP Agreement, and builds the zip itself. pdf-lib and fflate load only
// when a download starts.

async function fetchBytes(url) {
  // Plain fetch, not the API client: no sign-in header goes to R2 — the
  // signed link is the permission.
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Storage answered ${res.status} for a document`)
  return new Uint8Array(await res.arrayBuffer())
}

// The admin's stamped first page(s), then the generated agreement — the same
// result as the server's merge_pdf_front.
export async function stampInFront(stamp, base) {
  const { PDFDocument } = await import('pdf-lib')
  const out = await PDFDocument.create()
  for (const bytes of [stamp, base]) {
    const src = await PDFDocument.load(bytes, { ignoreEncryption: true })
    const pages = await out.copyPages(src, src.getPageIndices())
    pages.forEach((page) => out.addPage(page))
  }
  return out.save()
}

// files: [{ name, url, stamp_url? }] from a /links endpoint → a zip Blob.
export async function zipFromLinks(files) {
  const { zipSync } = await import('fflate')
  const stamps = new Map()
  const stamp = (url) => {
    if (!stamps.has(url)) stamps.set(url, fetchBytes(url))
    return stamps.get(url)
  }
  const entries = await Promise.all(files.map(async (f) => {
    let data = await fetchBytes(f.url)
    if (f.stamp_url) data = await stampInFront(await stamp(f.stamp_url), data)
    return [f.name, data]
  }))
  // PDFs are already compressed: store them as they are, like the server zip.
  return new Blob([zipSync(Object.fromEntries(entries), { level: 0 })], { type: 'application/zip' })
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
