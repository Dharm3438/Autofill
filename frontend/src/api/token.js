// The sign-in token. The backend returns it from login / sign-up / password
// change, and api/client.js sends it on every request as
// "Authorization: Bearer <token>".
//
// Why not a cookie: the frontend and the API are on different sites, and Safari,
// private/incognito windows and Brave throw away cookies from another site, so a
// cookie login kept bouncing people back to the login screen. A header the app
// adds itself isn't affected by that.
//
// localStorage keeps people signed in across tabs and browser restarts (an
// incognito window forgets it when closed). Storage can be unavailable (blocked
// site data), so every access is guarded; then sign-in lasts until a reload.

const KEY = 'auth_token'
let memoryToken = null

export function getToken() {
  try {
    return localStorage.getItem(KEY) || memoryToken
  } catch {
    return memoryToken
  }
}

export function setToken(token) {
  memoryToken = token
  try { localStorage.setItem(KEY, token) } catch { /* memory copy is enough */ }
}

export function clearToken() {
  memoryToken = null
  try { localStorage.removeItem(KEY) } catch { /* nothing stored */ }
}
