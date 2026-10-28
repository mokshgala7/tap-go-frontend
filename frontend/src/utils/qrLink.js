// Helpers for the QR payment link the driver's terminal shows: <site>/p/<token>.
// The token has to survive a login (and a page refresh) in the passenger's tab, so it lives in
// sessionStorage next to the other tapgo_* keys.

export const QR_PATH_PREFIX = '/p'
const PENDING_KEY = 'tapgo_pending_qr'
const TOKEN_RE = /^[A-Za-z0-9_-]{16,128}$/

/**
 * Pull a payment token out of whatever a QR/link contains: the https link (<site>/p/<token>),
 * a bare /p/<token> path, the older tapgo://pay?token=<token> and <site>/#/pay?token=<token>
 * forms, or the token itself. Returns null when it is not a Tap&Go payment link.
 */
export function extractQrToken(raw) {
  if (typeof raw !== 'string') return null
  const text = raw.trim()
  if (!text) return null
  if (TOKEN_RE.test(text)) return text

  const fromPath = (path) => {
    const m = /^\/p\/([^/?#]+)\/?$/.exec(path)
    return m && TOKEN_RE.test(m[1]) ? m[1] : null
  }

  if (text.startsWith('/')) return fromPath(text.split(/[?#]/)[0])

  try {
    if (text.startsWith('tapgo://pay')) {
      const token = new URLSearchParams(text.slice(text.indexOf('?') + 1)).get('token')
      return token && TOKEN_RE.test(token) ? token : null
    }
    const u = new URL(text)
    const byPath = fromPath(u.pathname)
    if (byPath) return byPath
    const search = u.hash.includes('?') ? u.hash.slice(u.hash.indexOf('?')) : u.search
    const token = new URLSearchParams(search).get('token')
    return token && TOKEN_RE.test(token) ? token : null
  } catch {
    return null
  }
}

/** The token in the address bar, if the page was opened from a payment link. */
export function readQrTokenFromLocation() {
  if (typeof window === 'undefined') return null
  return extractQrToken(window.location.pathname)
}

export function getPendingQrToken() {
  try {
    return sessionStorage.getItem(PENDING_KEY) || null
  } catch {
    return null
  }
}

export function setPendingQrToken(token) {
  try {
    sessionStorage.setItem(PENDING_KEY, token)
  } catch {
    // storage unavailable: the token is still in the address bar for this page load
  }
}

export function clearPendingQrToken() {
  try {
    sessionStorage.removeItem(PENDING_KEY)
  } catch {
    // nothing to clear
  }
  // Drop /p/<token> from the address bar so a refresh no longer reopens the payment.
  try {
    if (readQrTokenFromLocation()) window.history.replaceState(null, '', '/')
  } catch {
    // history unavailable
  }
}
