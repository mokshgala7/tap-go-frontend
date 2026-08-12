import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

// Views that require authentication
const PROTECTED_VIEWS = new Set(['passenger', 'driver', 'admin'])

// Views that are public
const PUBLIC_VIEWS = new Set([
  'home',
  'login',
  'register',
  'registration-review',
  'forgot-password',
  'about',
  'contact',
  'privacy',
  'terms',
  'refund-policy',
  'shipping-policy',
  'pricing',
  'payments',
  'lost-card',
  'faq',
])

const ROUTE_TO_VIEW = {
  '/': 'home',
  '/home': 'home',
  '/login': 'login',
  '/register': 'register',
  '/registration-review': 'registration-review',
  '/forgot-password': 'forgot-password',
  '/about': 'about',
  '/contact': 'contact',
  '/privacy': 'privacy',
  '/terms': 'terms',
  '/refund-policy': 'refund-policy',
  '/shipping-policy': 'shipping-policy',
  '/pricing': 'pricing',
  '/payments': 'payments',
  '/lost-card': 'lost-card',
  '/faq': 'faq',
  '/passenger': 'passenger',
  '/driver': 'driver',
  '/admin': 'admin',
}

// Checks if a target view is permitted based on current sessionStorage auth state
export function isViewAllowed(targetView) {
  if (!targetView || !Object.values(ROUTE_TO_VIEW).includes(targetView)) {
    return false // Unknown 404 route
  }

  if (PUBLIC_VIEWS.has(targetView)) {
    return true
  }

  if (PROTECTED_VIEWS.has(targetView)) {
    try {
      if (typeof window === 'undefined') return false

      if (targetView === 'admin') {
        const adminSession = sessionStorage.getItem('tapgo_admin_session')
        if (adminSession) return true
        const storedUser = sessionStorage.getItem('tapgo_user')
        if (storedUser) {
          const parsed = JSON.parse(storedUser)
          return parsed.account_type === 'admin' || parsed.role === 'admin' || parsed.email === 'admin@tapandgo.com'
        }
        return false
      }

      const storedUser = sessionStorage.getItem('tapgo_user')
      if (!storedUser) return false

      const parsed = JSON.parse(storedUser)
      const userRole = (parsed.account_type || parsed.role || '').toLowerCase()

      if (targetView === 'passenger') {
        return userRole === 'passenger' || userRole === 'user' || userRole === ''
      }
      if (targetView === 'driver') {
        return userRole === 'driver'
      }
    } catch {
      return false
    }
  }

  return false
}

function resolveInitialView() {
  if (typeof window === 'undefined') return 'home'

  // Priority 1: Check sessionStorage persisted view (supports page refresh F5 / Cmd+R)
  try {
    const storedView = sessionStorage.getItem('tapgo_view')
    if (storedView && isViewAllowed(storedView)) {
      return storedView
    }
  } catch {}

  // Priority 2: Check URL hash if directly provided and view is allowed
  const hashRaw = window.location.hash.replace(/^#\/?/, '').split('?')[0]
  if (hashRaw) {
    const matched =
      ROUTE_TO_VIEW[`/${hashRaw}`] ||
      (Object.values(ROUTE_TO_VIEW).includes(hashRaw) ? hashRaw : null)
    if (matched && isViewAllowed(matched)) {
      return matched
    }
  }

  // Fallback for unauthenticated access to protected routes, 404s, or clean opening: 'home'
  return 'home'
}

const NavContext = createContext(null)

export function NavProvider({ children }) {
  const [view, setViewState] = useState(() => resolveInitialView())
  const [state, setState] = useState(null)

  const setView = useCallback((nextView) => {
    const allowed = isViewAllowed(nextView) ? nextView : 'home'
    setViewState(allowed)
    try {
      sessionStorage.setItem('tapgo_view', allowed)
      if (typeof window !== 'undefined') {
        const targetHash = allowed === 'home' ? '#/' : `#/${allowed}`
        if (window.location.hash !== targetHash) {
          window.history.replaceState(null, '', targetHash)
        }
      }
    } catch {}
  }, [])

  useEffect(() => {
    if (typeof window !== 'undefined' && view) {
      sessionStorage.setItem('tapgo_view', view)
      const targetHash = view === 'home' ? '#/' : `#/${view}`
      if (window.location.hash !== targetHash) {
        window.history.replaceState(null, '', targetHash)
      }
    }
  }, [view])

  // Prevent back button from opening protected views after logout
  useEffect(() => {
    if (typeof window === 'undefined') return

    const handlePopStateOrHashChange = () => {
      const hashRaw = window.location.hash.replace(/^#\/?/, '').split('?')[0]
      const matched =
        ROUTE_TO_VIEW[`/${hashRaw}`] ||
        (Object.values(ROUTE_TO_VIEW).includes(hashRaw) ? hashRaw : null)

      if (matched && isViewAllowed(matched)) {
        setViewState(matched)
        sessionStorage.setItem('tapgo_view', matched)
      } else {
        // Access denied (e.g. back button to protected view after logout, or unknown 404)
        setViewState('home')
        sessionStorage.setItem('tapgo_view', 'home')
        window.history.replaceState(null, '', '#/')
      }
    }

    window.addEventListener('popstate', handlePopStateOrHashChange)
    window.addEventListener('hashchange', handlePopStateOrHashChange)

    return () => {
      window.removeEventListener('popstate', handlePopStateOrHashChange)
      window.removeEventListener('hashchange', handlePopStateOrHashChange)
    }
  }, [])

  const navigate = useCallback(
    (to, options) => {
      const key = typeof to === 'string' ? to.split('?')[0].split('#')[0] : '/'
      const targetView =
        ROUTE_TO_VIEW[key] || (typeof to === 'string' ? to.replace(/^\//, '') : 'home')
      setView(targetView)
      setState(
        options && Object.prototype.hasOwnProperty.call(options, 'state') ? options.state : null
      )
      if (typeof window !== 'undefined') {
        window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' })
      }
    },
    [setView]
  )

  const value = useMemo(() => ({ view, navigate, state }), [view, navigate, state])

  return <NavContext.Provider value={value}>{children}</NavContext.Provider>
}

function useNavContext() {
  const ctx = useContext(NavContext)
  if (!ctx) throw new Error('Navigation hooks must be used inside a NavProvider')
  return ctx
}

export function useNavigate() {
  return useNavContext().navigate
}

export function useCurrentView() {
  return useNavContext().view
}

export function useNavState() {
  return useNavContext().state
}

// Drop-in replacement for react-router-dom's <Link>.
export function Link({ to, children, onClick, ...rest }) {
  const navigate = useNavigate()

  const handleClick = (event) => {
    onClick?.(event)
    if (event.defaultPrevented) return
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return
    event.preventDefault()
    navigate(to)
  }

  return (
    <a href={typeof to === 'string' ? to : '#'} onClick={handleClick} {...rest}>
      {children}
    </a>
  )
}


