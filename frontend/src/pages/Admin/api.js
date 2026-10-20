export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://api.thetapandgo.in'


// The admin session token issued by /api/admin/login, kept (with the admin
// profile) in sessionStorage by Admin.jsx / Login.jsx.
export function adminAuthHeaders() {
  try {
    const session = JSON.parse(sessionStorage.getItem('tapgo_admin_session') || 'null')
    return session?.token ? { Authorization: `Bearer ${session.token}` } : {}
  } catch {
    return {}
  }
}

export async function adminRequest(path, adminId, options = {}) {
  const headers = { ...(options.headers || {}), ...(adminId ? adminAuthHeaders() : {}) }
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_BASE}/api/admin${path}`, { ...options, headers })
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : await response.text()
  if (response.status === 401 && adminId) {
    // The admin session ended (expired, signed out elsewhere, or issued before this change).
    try { sessionStorage.removeItem('tapgo_admin_session') } catch { /* ignore */ }
    window.location.reload()
  }
  if (!response.ok) throw new Error(data?.detail || 'The server could not complete that request.')
  return data
}

export function fileUrl(path) {
  if (!path) return null
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) {
    return path
  }
  if (path.startsWith('uploads/')) {
    return `${API_BASE}/${path.replace(/^\//, '')}`
  }
  return null
}
