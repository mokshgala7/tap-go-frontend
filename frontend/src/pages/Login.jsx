import { useEffect, useState } from 'react'
import { Link, useNavigate } from '../routes/navigation.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import Footer from '../components/Common/Footer.jsx'
import Navbar from '../components/Common/Navbar.jsx'
import illustration from '../assets/images/login-fintech-taxi.svg'
import logo from '../assets/images/logio.png'
import '../styles/Login.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://api.thetapandgo.in'

const trustBadges = ['🔒 Secure Login', '🛡 AI Powered', '🚖 Trusted by Taxi Drivers']

const initialErrors = {
  account: '',
  password: '',
}

function validateLogin({ account, password }) {
  const nextErrors = { ...initialErrors }
  const accountValue = account.trim()
  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(accountValue)
  const validMobile = /^[0-9]{10}$/.test(accountValue)

  if (!accountValue) {
    nextErrors.account = 'Email or mobile number is required.'
  } else if (!validEmail && !validMobile) {
    nextErrors.account = 'Enter a valid email or 10-digit mobile number.'
  }

  if (!password) {
    nextErrors.password = 'Password is required.'
  } else if (password.length < 3) {
    nextErrors.password = 'Password must be at least 3 characters.'
  }

  return nextErrors
}

function Login() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [formData, setFormData] = useState({ account: '', password: '' })
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [errors, setErrors] = useState(initialErrors)
  const [successMessage, setSuccessMessage] = useState('')
  const [copiedField, setCopiedField] = useState(null)

  const handleCopy = (text, field) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text).catch(() => {})
    }
    setCopiedField(field)
    setTimeout(() => {
      setCopiedField((current) => (current === field ? null : current))
    }, 2000)
  }

  const handleFillReviewCredentials = () => {
    setFormData({
      account: 'amazon.review@thetapandgo.in',
      password: 'TapGo@2026Review',
    })
    setErrors(initialErrors)
  }

  useEffect(() => {
    const reviewNotice = sessionStorage.getItem('tapgo_registration_notice')
    if (reviewNotice) {
      setSuccessMessage(reviewNotice)
      sessionStorage.removeItem('tapgo_registration_notice')
    }
  }, [])

  const updateField = (event) => {
    const { name, value } = event.target

    setFormData((current) => ({
      ...current,
      [name]: value,
    }))

    if (errors[name]) {
      setErrors((current) => ({
        ...current,
        [name]: '',
      }))
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSuccessMessage('')

    const validationErrors = validateLogin(formData)
    setErrors(validationErrors)

    if (validationErrors.account || validationErrors.password) {
      return
    }

    setIsLoading(true)

    const res = await login(formData)
    setIsLoading(false)

    if (res.success && res.user) {
      setSuccessMessage(rememberMe ? 'Login validated. This device will be remembered.' : 'Login validated securely.')
      const targetRole = (res.user.account_type || res.user.role || '').toLowerCase()
      if (targetRole === 'admin') {
        sessionStorage.setItem('tapgo_admin_session', JSON.stringify({ email: res.user.email, name: res.user.name || 'Admin', id: res.user.id }))
        navigate('/admin')
      } else if (targetRole === 'driver') {
        navigate('/driver')
      } else {
        navigate('/passenger')
      }
    } else if (res.redirect_admin) {
      // User typed admin credentials manually — call admin API to get real admin id
      try {
        const adminRes = await fetch(`${API_BASE}/api/admin/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: formData.account, password: formData.password }),
        })
        const adminData = await adminRes.json()
        if (adminData.success && adminData.admin) {
          sessionStorage.setItem('tapgo_admin_session', JSON.stringify(adminData.admin))
          navigate('/admin')
        } else {
          setErrors((current) => ({ ...current, password: 'Admin login failed. Use the Admin Console.' }))
        }
      } catch {
        setErrors((current) => ({ ...current, password: 'Backend unavailable.' }))
      }
    } else {
      setErrors((current) => ({
        ...current,
        password: res.message || 'Invalid Credentials',
      }))
    }
  }

  return (
    <div className="tapgo-login tapgo-shell font-body-lg antialiased selection:bg-secondary-container selection:text-on-secondary-container">
      <Navbar />

      <main className="login-main">
        <div className="login-background" aria-hidden="true">
          <div className="login-blob login-blob-primary"></div>
          <div className="login-blob login-blob-secondary"></div>
          <div className="login-dot login-dot-one"></div>
          <div className="login-dot login-dot-two"></div>
          <div className="login-dot login-dot-three"></div>
        </div>

        <section className="login-layout" aria-label="Tap&Go login">
          <div className="login-visual" aria-hidden="true">
            <div className="login-illustration-wrap">
              <img className="login-illustration" src={illustration} alt="" />
            </div>
          </div>

          <div className="login-panel">
            <Link className="login-brand" to="/" aria-label="Tap&Go home">
              <img className="login-brand-logo" src={logo} alt="" />
              <span className="login-brand-name">
                Tap<span>&amp;</span>Go
              </span>
            </Link>

            <article className="login-card">
              <div
                className={`login-progress ${isLoading ? 'login-progress-active' : ''}`}
                aria-hidden="true"
              ></div>

              <header className="login-header">
                <h1>Welcome Back</h1>
                <p>Sign in to continue using Tap&Go.</p>
              </header>

              <form className="login-form" onSubmit={handleSubmit} noValidate>
                <div className="login-field">
                  <label htmlFor="account">Email Address or Mobile Number</label>
                  <div className={`login-input-box ${errors.account ? 'login-input-box-error' : ''}`}>
                    <span className="material-symbols-outlined login-input-icon" aria-hidden="true">
                      mail
                    </span>
                    <input
                      className="login-input-field"
                      id="account"
                      name="account"
                      type="text"
                      autoComplete="username"
                      placeholder="name@example.com or 9876543210"
                      value={formData.account}
                      onChange={updateField}
                      aria-invalid={Boolean(errors.account)}
                      aria-describedby={errors.account ? 'account-error' : undefined}
                    />
                  </div>
                  <p className="login-error" id="account-error" role="alert">
                    {errors.account}
                  </p>
                </div>

                <div className="login-field">
                  <label htmlFor="password">Password</label>
                  <div className={`login-input-box ${errors.password ? 'login-input-box-error' : ''}`}>
                    <span className="material-symbols-outlined login-input-icon" aria-hidden="true">
                      lock
                    </span>
                    <input
                      className="login-input-field"
                      id="password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      placeholder="••••••••"
                      value={formData.password}
                      onChange={updateField}
                      aria-invalid={Boolean(errors.password)}
                      aria-describedby={errors.password ? 'password-error' : undefined}
                    />
                    <button
                      className="login-password-toggle"
                      type="button"
                      onClick={() => setShowPassword((current) => !current)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">
                        {showPassword ? 'visibility_off' : 'visibility'}
                      </span>
                    </button>
                  </div>
                  <p className="login-error" id="password-error" role="alert">
                    {errors.password}
                  </p>
                </div>

                <div className="login-options">
                  <label className="login-checkbox">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(event) => setRememberMe(event.target.checked)}
                    />
                    <span className="login-checkbox-box" aria-hidden="true">
                      <span className="material-symbols-outlined">check</span>
                    </span>
                    <span>Remember Me</span>
                  </label>

                  <Link className="login-forgot" to="/forgot-password">
                    Forgot Password?
                  </Link>
                </div>

                <button className="login-button" type="submit" disabled={isLoading}>
                  <span>{isLoading ? 'Signing In...' : 'Login'}</span>
                  {isLoading && (
                    <span className="material-symbols-outlined login-spinner" aria-hidden="true">
                      progress_activity
                    </span>
                  )}
                </button>

                
              </form>

              {/* Amazon Verification Test Account */}
              <section className="login-verification-card" aria-label="Amazon Verification Test Account">
                <div className="login-verification-header">
                  <div className="login-verification-badge-title">
                    <span className="material-symbols-outlined login-verification-icon" aria-hidden="true">
                      verified_user
                    </span>
                    <div>
                      <h2 className="login-verification-title">Amazon Verification Test Account</h2>
                      <p className="login-verification-subtitle">Pre-configured testing credentials for app reviewer verification</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="login-verification-autofill-btn"
                    onClick={handleFillReviewCredentials}
                    title="Fill credentials into login form"
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">login</span>
                    <span>Fill form</span>
                  </button>
                </div>

                <div className="login-verification-body">
                  <div className="login-verification-row">
                    <div className="login-verification-label-group">
                      <span className="login-verification-label">Email:</span>
                      <span className="login-verification-value">amazon.review@thetapandgo.in</span>
                    </div>
                    <button
                      type="button"
                      className={`login-verification-copy-btn ${copiedField === 'email' ? 'login-verification-copied' : ''}`}
                      onClick={() => handleCopy('amazon.review@thetapandgo.in', 'email')}
                      aria-label="Copy reviewer email"
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">
                        {copiedField === 'email' ? 'done' : 'content_copy'}
                      </span>
                      <span>{copiedField === 'email' ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>

                  <div className="login-verification-row">
                    <div className="login-verification-label-group">
                      <span className="login-verification-label">Password:</span>
                      <span className="login-verification-value login-verification-password">TapGo@2026Review</span>
                    </div>
                    <button
                      type="button"
                      className={`login-verification-copy-btn ${copiedField === 'password' ? 'login-verification-copied' : ''}`}
                      onClick={() => handleCopy('TapGo@2026Review', 'password')}
                      aria-label="Copy reviewer password"
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">
                        {copiedField === 'password' ? 'done' : 'content_copy'}
                      </span>
                      <span>{copiedField === 'password' ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                </div>

                <div className="login-verification-meta">
                  <span className="login-verification-tag">
                    <span className="material-symbols-outlined" aria-hidden="true">account_circle</span>
                    Role: Passenger (User)
                  </span>
                  <span className="login-verification-tag">
                    <span className="material-symbols-outlined" aria-hidden="true">account_balance_wallet</span>
                    Pre-funded Wallet (₹500)
                  </span>
                  <span className="login-verification-tag">
                    <span className="material-symbols-outlined" aria-hidden="true">qr_code_scanner</span>
                    NFC &amp; QR Ready
                  </span>
                </div>
              </section>

              <div className="login-card-footer">
                <p>
                  Don&apos;t have an account? <Link to="/register">Sign Up</Link>
                </p>
                <p>
                  Platform administrator? <Link to="/admin">Open Admin Console</Link>
                </p>
                {successMessage && (
                  <p className="login-success" role="status">
                    {successMessage}
                  </p>
                )}
              </div>
            </article>



            <div className="login-trust" aria-label="Security badges">
              {trustBadges.map((badge, index) => (
                <div className="login-trust-item" key={badge}>
                  <span>{badge}</span>
                  {index < trustBadges.length - 1 && (
                    <span className="login-trust-divider" aria-hidden="true"></span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default Login
