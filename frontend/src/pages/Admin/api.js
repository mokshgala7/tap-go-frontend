export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://tap-go-backend.onrender.com'


export async function adminRequest(path, adminId, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (adminId) headers['X-Admin-Id'] = String(adminId)
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_BASE}/api/admin${path}`, { ...options, headers })
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(data?.detail || 'The server could not complete that request.')
  return data
}

export function fileUrl(path) {
  return path ? `${API_BASE}/${path.replace(/^\//, '')}` : null
}
