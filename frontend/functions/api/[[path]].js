// Cloudflare Pages Function: forwards every /api/* request to the backend on
// Render, so the browser only ever talks to the frontend's own domain.
//
// Why: the login cookie must be first-party. When the app called the Render
// domain directly, Safari and private/incognito windows treated the cookie as
// a third-party cookie and threw it away, so people landed back on the login
// screen right after signing in. (Pages' _redirects can't proxy to another
// domain, hence this function.)
//
// The backend URL can be overridden with a BACKEND_URL environment variable in
// the Pages project settings; otherwise the default below is used.

const DEFAULT_BACKEND = 'https://autofill-blgf.onrender.com'

export async function onRequest({ request, env }) {
  const backend = new URL(env.BACKEND_URL || DEFAULT_BACKEND)
  const incoming = new URL(request.url)
  const target = new URL(incoming.pathname + incoming.search, backend)

  const headers = new Headers(request.headers)
  // Let fetch set Host for the backend, and don't pass Cloudflare's own
  // per-hop headers on to another Cloudflare-fronted site (Render).
  headers.delete('host')
  for (const name of [...headers.keys()]) {
    if (name.startsWith('cf-')) headers.delete(name)
  }
  // The real visitor's IP, set by Cloudflare (clients can't forge it). The
  // backend's rate limits read it as the entry before Render's own
  // (TRUSTED_PROXY_HOPS=1 in backend/app/core/config.py).
  const clientIp = request.headers.get('cf-connecting-ip')
  if (clientIp) headers.set('x-forwarded-for', clientIp)
  else headers.delete('x-forwarded-for')

  const hasBody = !['GET', 'HEAD'].includes(request.method)
  const response = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    redirect: 'manual',
  })

  // A redirect from the backend (e.g. a trailing-slash fix) would point at the
  // Render domain; keep the browser on ours.
  const location = response.headers.get('location')
  if (location) {
    const loc = new URL(location, target)
    if (loc.origin === backend.origin) {
      const out = new Response(response.body, response)
      out.headers.set('location', incoming.origin + loc.pathname + loc.search)
      return out
    }
  }
  return response
}
