import { createContext, useContext, useEffect, useState } from 'react'

const STORAGE_KEY = 'tapgo_user'
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://tap-go-backend.onrender.com'


const AuthContext = createContext(null)

export function resolveFileUrl(filePath) {
  if (!filePath) return null
  if (filePath.startsWith('http://') || filePath.startsWith('https://') || filePath.startsWith('data:')) {
    return filePath
  }
  return `${API_BASE}/${filePath.replace(/^\//, '')}`
}

function normalizeUser(userData) {
  if (!userData) return null
  const photoPath = userData.profile_photo || userData.photoUrl
  const photoUrl = resolveFileUrl(photoPath)

  return {
    ...userData,
    photoUrl,
    account: userData.email || userData.phone,
    role: userData.account_type === 'driver' ? 'driver' : 'passenger',
  }
}

function readStoredUser() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    // Clean up any legacy localStorage entry
    localStorage.removeItem(STORAGE_KEY)
    return raw ? normalizeUser(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => readStoredUser())

  useEffect(() => {
    if (user) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user))
    } else {
      sessionStorage.removeItem(STORAGE_KEY)
    }
    localStorage.removeItem(STORAGE_KEY)
  }, [user])

  const login = async ({ account, password }) => {
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account, password }),
      })
      const data = await response.json()
      if (data.success && data.user) {
        const nextUser = normalizeUser(data.user)
        try {
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(nextUser))
          if (nextUser.account_type === 'admin' || nextUser.role === 'admin') {
            sessionStorage.setItem('tapgo_admin_session', JSON.stringify({ email: nextUser.email, name: nextUser.name || 'Admin', id: nextUser.id }))
          }
        } catch {}
        setUser(nextUser)
        return { success: true, user: nextUser }
      } else {
        return { success: false, message: data.message || 'Invalid Credentials', redirect_admin: Boolean(data.redirect_admin) }
      }
    } catch (err) {
      return { success: false, message: 'Backend server unavailable.' }
    }
  }

  const register = async (formDataPayload) => {
    try {
      let bodyData = formDataPayload
      if (!(formDataPayload instanceof FormData)) {
        bodyData = new FormData()
        Object.keys(formDataPayload).forEach((key) => {
          if (formDataPayload[key] !== null && formDataPayload[key] !== undefined) {
            bodyData.append(key, formDataPayload[key])
          }
        })
      }

      const response = await fetch(`${API_BASE}/api/auth/register`, {
        method: 'POST',
        body: bodyData,
      })
      const data = await response.json()
      if (response.ok && data.success) {
        const nextUser = normalizeUser(data.user)
        return { success: true, user: nextUser, message: data.message, review_demo: Boolean(data.review_demo) }
      } else {
        let errorMsg = 'Registration failed'
        if (typeof data.detail === 'string') {
          errorMsg = data.detail
        } else if (Array.isArray(data.detail)) {
          errorMsg = data.detail.map((item) => item.msg || 'Invalid field').join('; ')
        } else if (data.message) {
          errorMsg = data.message
        }
        return { success: false, message: errorMsg }
      }
    } catch (err) {
      return { success: false, message: 'Backend server unavailable.' }
    }
  }

  const saveProfileToDb = async (patch) => {
    if (!user?.id) return { success: false, message: 'User not logged in' }
    try {
      const res = await fetch(`${API_BASE}/api/auth/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, ...patch }),
      })
      const data = await res.json()
      if (res.ok && data.success) {
        const nextUser = normalizeUser(data.user)
        setUser(nextUser)
        return { success: true, user: nextUser }
      } else {
        return { success: false, message: data.detail || data.message || 'Failed to update profile' }
      }
    } catch (err) {
      return { success: false, message: 'Error saving profile to server.' }
    }
  }

  const requestAdminAccess = async (requestType) => {
    if (!user?.id) return { success: false, message: 'User not logged in' }
    try {
      const res = await fetch(`${API_BASE}/api/auth/request-admin-access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, request_type: requestType }),
      })
      const data = await res.json()
      if (res.ok && data.success) {
        const nextUser = normalizeUser(data.user)
        setUser(nextUser)
        return { success: true, message: data.message, user: nextUser }
      } else {
        return { success: false, message: data.detail || 'Request failed' }
      }
    } catch (err) {
      return { success: false, message: 'Server error' }
    }
  }

  const refreshProfile = async () => {
    if (!user?.id) return null
    try {
      const res = await fetch(`${API_BASE}/api/auth/profile/${user.id}`)
      const data = await res.json()
      if (res.ok && data.success && data.user) {
        const nextUser = normalizeUser(data.user)
        setUser(nextUser)
        return nextUser
      }
    } catch {
      // Ignore background network failure
    }
    return user
  }

  const logout = () => {
    setUser(null)
    try {
      sessionStorage.clear()
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem('tapgo_admin_session')
    } catch {
      // Ignore storage error
    }
  }

  const updateProfile = (patch) => {
    setUser((current) => (current ? normalizeUser({ ...current, ...patch }) : current))
  }

  return (
    <AuthContext.Provider value={{ user, login, register, logout, updateProfile, saveProfileToDb, requestAdminAccess, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside an AuthProvider')
  return ctx
}
