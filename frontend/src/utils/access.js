// Permission names — must match backend/app/core/permissions.py (class P).
// The backend sends each user's computed permission list from /auth/me; the UI
// only uses it to decide what to show. Every API call is enforced server-side.
export const PERM = {
  CUSTOMERS_READ_ALL: 'customers:read_all',
  CUSTOMERS_READ_OWN: 'customers:read_own',
  CUSTOMERS_CREATE: 'customers:create',
  CUSTOMERS_UPDATE: 'customers:update',
  CUSTOMERS_DELETE: 'customers:delete',
  INSTALLATIONS_READ: 'installations:read',
  INSTALLATIONS_WRITE: 'installations:write',
  DOCUMENTS_MANAGE: 'documents:manage',
  UPLOADS_MANAGE: 'uploads:manage',
  SIGNING_SEND: 'signing:send',
  DASHBOARD_VIEW: 'dashboard:view',
  USERS_MANAGE: 'users:manage',
}

export const CUSTOMERS_VIEW = [PERM.CUSTOMERS_READ_ALL, PERM.CUSTOMERS_READ_OWN]

// `perm` may be a single permission or an array (any-of).
export function hasPerm(user, perm) {
  const granted = user?.permissions || []
  if (Array.isArray(perm)) return perm.some((p) => granted.includes(p))
  return granted.includes(perm)
}

// Where a user lands after login or when they hit a page they can't open.
export function homePath(user) {
  if (hasPerm(user, PERM.DASHBOARD_VIEW)) return '/dashboard'
  if (hasPerm(user, CUSTOMERS_VIEW)) return '/customers'
  if (hasPerm(user, PERM.INSTALLATIONS_READ)) return '/installations'
  return '/welcome'
}
