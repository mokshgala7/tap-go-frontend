import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from '../../routes/navigation.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import { useWallet } from '../../context/WalletContext.jsx'
import RazorpayAddMoneyModal from '../../components/Payment/RazorpayAddMoneyModal.jsx'
import {
  clearPendingQrToken,
  getPendingQrToken,
  readQrTokenFromLocation,
  setPendingQrToken,
} from '../../utils/qrLink.js'
import './QrPay.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://api.thetapandgo.in'

function sessionToken() {
  try { return sessionStorage.getItem('tapgo_token') || '' } catch { return '' }
}

// One key per page load: double taps and retries replay the same payment instead of charging twice.
function newIdempotencyKey() {
  const c = globalThis.crypto
  if (c?.randomUUID) return c.randomUUID()
  const bytes = new Uint8Array(16)
  c.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

const rupees = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const clock = (secs) => {
  const s = Math.max(0, Math.floor(secs))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// phase: loading | ready | paying | success | insufficient | expired | paid | cancelled |
//        invalid | failed | busy | network | wrongrole
const END_COPY = {
  expired: { icon: '⏱', title: 'This QR code has expired', body: 'Ask the driver to show a new code and scan it again.' },
  paid: { icon: '✓', title: 'Already paid', body: 'This fare has already been paid. Nothing more is needed.' },
  cancelled: { icon: '✕', title: 'Cancelled by the driver', body: 'The driver cancelled this payment request. You have not been charged.' },
  invalid: { icon: '?', title: 'Invalid link', body: 'This payment link is not valid. Please scan the code on the driver’s terminal again.' },
  failed: { icon: '!', title: 'Payment could not be completed', body: 'You have not been charged. Ask the driver for a new code.' },
}

function QrPay() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { refreshWallet } = useWallet()

  const [token] = useState(() => readQrTokenFromLocation() || getPendingQrToken())
  const [phase, setPhase] = useState('loading')
  const [info, setInfo] = useState(null)
  const [balance, setBalance] = useState(0)
  const [secondsLeft, setSecondsLeft] = useState(0)
  const [message, setMessage] = useState('')
  const [result, setResult] = useState(null)
  const [showTopUp, setShowTopUp] = useState(false)

  const idempotencyKey = useRef(null)
  if (idempotencyKey.current === null) idempotencyKey.current = newIdempotencyKey()
  const deadline = useRef(0) // performance.now() value at which the request expires
  const payingRef = useRef(false)
  const phaseRef = useRef('loading')
  const setPhaseBoth = useCallback((next) => {
    phaseRef.current = next
    setPhase(next)
  }, [])

  const authHeaders = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken()}` })

  const backToLogin = useCallback(() => {
    if (token) setPendingQrToken(token)
    try {
      sessionStorage.setItem('tapgo_registration_notice', 'Log in to complete your payment.')
    } catch { /* optional hint */ }
    navigate('/login')
  }, [navigate, token])

  const applyGone = useCallback((status) => {
    const map = { Expired: 'expired', Completed: 'paid', Cancelled: 'cancelled', Failed: 'failed', Processing: 'busy' }
    setPhaseBoth(map[status] || 'failed')
  }, [setPhaseBoth])

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/qr/${encodeURIComponent(token)}`, { headers: authHeaders() })
      if (res.status === 401) return backToLogin()
      const data = await res.json().catch(() => ({}))
      if (res.status === 404) return setPhaseBoth('invalid')
      if (res.status === 403) {
        setMessage(data.detail || '')
        return setPhaseBoth('wrongrole')
      }
      if (res.status === 410) return applyGone(data.status)
      if (!res.ok || !data.success) {
        setMessage(data.detail || 'Could not load this payment.')
        return setPhaseBoth('network')
      }
      const p = data.payment
      deadline.current = performance.now() + Number(p.seconds_remaining ?? p.remaining_seconds ?? 0) * 1000
      setInfo(p)
      setBalance(Number(p.wallet_balance || 0))
      setSecondsLeft(Number(p.seconds_remaining ?? p.remaining_seconds ?? 0))
      setPhaseBoth('ready')
    } catch {
      setMessage('Could not reach the server. Check your connection and try again.')
      setPhaseBoth('network')
    }
  }, [token, backToLogin, applyGone, setPhaseBoth])

  const reload = () => {
    setPhaseBoth('loading')
    load()
  }

  const isDriver = (user?.account_type || user?.role) === 'driver'

  // Gate on sign-in, then load the payment once. The token stays stored across the login detour.
  useEffect(() => {
    if (!token) return
    setPendingQrToken(token)
    if (!user) return backToLogin()
    if (isDriver) return
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.id])

  // Live countdown driven by the server's seconds_remaining (immune to a wrong phone clock).
  useEffect(() => {
    if (!['ready', 'insufficient', 'paying', 'retry'].includes(phase)) return undefined
    const tick = () => {
      const left = Math.max(0, Math.ceil((deadline.current - performance.now()) / 1000))
      setSecondsLeft(left)
      // A payment already in flight decides its own outcome; only idle screens flip to expired.
      if (left === 0 && phaseRef.current !== 'paying') setPhaseBoth('expired')
    }
    tick()
    const id = window.setInterval(tick, 500)
    return () => window.clearInterval(id)
  }, [phase, setPhaseBoth])

  const payNow = useCallback(async () => {
    if (payingRef.current) return
    payingRef.current = true
    setPhaseBoth('paying')
    setMessage('')
    try {
      const res = await fetch(`${API_BASE}/api/qr/${encodeURIComponent(token)}/confirm`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ idempotency_key: idempotencyKey.current }),
      })
      if (res.status === 401) return backToLogin()
      const data = await res.json().catch(() => ({}))

      if (res.ok && data.success) {
        const newBalance = Number(data.wallet?.balance ?? 0)
        setBalance(newBalance)
        setResult({
          amount: Number(data.transaction?.amount ?? info?.amount),
          driver: data.transaction?.driver_name || info?.driver_name || 'the driver',
          reference: data.transaction?.reference,
          balance: newBalance,
        })
        setPhaseBoth('success')
        refreshWallet?.()
      } else if (data.code === 'insufficient_balance') {
        setBalance(Number(data.balance || 0))
        setPhaseBoth('insufficient')
      } else if (res.status === 410) {
        applyGone(data.status)
      } else if (res.status === 404) {
        setPhaseBoth('invalid')
      } else if (res.status === 409) {
        setPhaseBoth('busy')
      } else {
        setMessage(data.detail || 'Payment failed.')
        setPhaseBoth('failed')
      }
    } catch {
      // The request may or may not have reached the server. Retrying with the same key is safe.
      setMessage('Could not reach the server. Your payment may not have gone through; tap Retry to check safely.')
      setPhaseBoth('retry')
    } finally {
      payingRef.current = false
    }
  }, [token, info, applyGone, backToLogin, refreshWallet, setPhaseBoth])

  const finish = () => {
    clearPendingQrToken()
    navigate('/passenger')
  }

  const switchAccount = async () => {
    await logout()
    if (token) setPendingQrToken(token)
    navigate('/login')
  }

  const short = info && balance < Number(info.amount)

  // Missing token / driver account are known from props alone, so they need no effect or state.
  const shown = !token ? 'invalid' : isDriver ? 'wrongrole' : phase

  let body
  if (shown === 'loading') {
    body = <p className="qrpay-note">Loading payment…</p>
  } else if (shown === 'success' && result) {
    body = (
      <>
        <div className="qrpay-icon qrpay-ok" aria-hidden="true">✓</div>
        <h1 className="qrpay-title">Payment successful</h1>
        <p className="qrpay-amount">{rupees(result.amount)}</p>
        <dl className="qrpay-rows">
          <div><dt>Paid to</dt><dd>{result.driver}</dd></div>
          <div><dt>New wallet balance</dt><dd>{rupees(result.balance)}</dd></div>
          {result.reference && <div><dt>Reference</dt><dd>{result.reference}</dd></div>}
        </dl>
        <button type="button" className="qrpay-btn" onClick={finish}>Done</button>
      </>
    )
  } else if (END_COPY[shown]) {
    const c = END_COPY[shown]
    body = (
      <>
        <div className={`qrpay-icon ${shown === 'paid' ? 'qrpay-ok' : 'qrpay-bad'}`} aria-hidden="true">{c.icon}</div>
        <h1 className="qrpay-title">{c.title}</h1>
        <p className="qrpay-note">{shown === 'failed' && message ? message : c.body}</p>
        <button type="button" className="qrpay-btn" onClick={finish}>Back to my wallet</button>
      </>
    )
  } else if (shown === 'wrongrole') {
    body = (
      <>
        <div className="qrpay-icon qrpay-bad" aria-hidden="true">!</div>
        <h1 className="qrpay-title">Passenger account needed</h1>
        <p className="qrpay-note">You are signed in with a driver account. Sign in with a passenger account to pay this fare.</p>
        <button type="button" className="qrpay-btn" onClick={switchAccount}>Sign in as a passenger</button>
      </>
    )
  } else if (shown === 'busy') {
    body = (
      <>
        <h1 className="qrpay-title">Payment is being processed</h1>
        <p className="qrpay-note">Please wait a moment, then check again. You will not be charged twice.</p>
        <button type="button" className="qrpay-btn" onClick={reload}>Check again</button>
      </>
    )
  } else if (shown === 'network') {
    body = (
      <>
        <h1 className="qrpay-title">Connection problem</h1>
        <p className="qrpay-note">{message}</p>
        <button type="button" className="qrpay-btn" onClick={reload}>Try again</button>
      </>
    )
  } else if (info) {
    // ready | paying | insufficient | retry
    const paying = shown === 'paying'
    body = (
      <>
        <p className="qrpay-label">Pay driver</p>
        <h1 className="qrpay-driver">{info.driver_name}</h1>
        <p className="qrpay-amount">{rupees(info.amount)}</p>
        <dl className="qrpay-rows">
          <div><dt>Vehicle number</dt><dd>{info.vehicle_registration || '—'}</dd></div>
          <div><dt>Vehicle type</dt><dd>{info.vehicle_type || '—'}</dd></div>
          <div><dt>Your wallet balance</dt><dd className={short ? 'qrpay-low' : ''}>{rupees(balance)}</dd></div>
          <div><dt>Time left</dt><dd className="qrpay-timer">{clock(secondsLeft)}</dd></div>
        </dl>

        {(shown === 'insufficient' || short) && (
          <div className="qrpay-warn" role="alert">
            <strong>Insufficient balance.</strong> You need {rupees(Number(info.amount) - balance)} more to pay this fare.
          </div>
        )}
        {shown === 'retry' && <div className="qrpay-warn" role="alert">{message}</div>}

        {(shown === 'insufficient' || short) && (
          <button type="button" className="qrpay-btn" onClick={() => setShowTopUp(true)}>Add Money</button>
        )}
        {!(shown === 'insufficient' || short) && (
          <button type="button" className="qrpay-btn" onClick={payNow} disabled={paying}>
            {paying ? 'Paying…' : shown === 'retry' ? `Retry ${rupees(info.amount)}` : `Pay Now ${rupees(info.amount)}`}
          </button>
        )}
        <button type="button" className="qrpay-link" onClick={finish} disabled={paying}>Cancel</button>
      </>
    )
  } else {
    body = <p className="qrpay-note">Loading payment…</p>
  }

  return (
    <div className="qrpay-page">
      <div className="qrpay-card">
        <div className="qrpay-brand">Tap&amp;Go</div>
        {body}
      </div>

      {showTopUp && (
        <RazorpayAddMoneyModal
          user={user}
          onClose={() => setShowTopUp(false)}
          onSuccess={(newBalance) => {
            setShowTopUp(false)
            const next = Number(newBalance)
            if (newBalance != null && Number.isFinite(next)) {
              setBalance(next)
              if (phaseRef.current === 'insufficient') setPhaseBoth('ready')
            } else {
              load() // balance unknown: reload the payment, which also returns the fresh balance
            }
            refreshWallet?.()
          }}
          onFailure={() => setShowTopUp(false)}
        />
      )}
    </div>
  )
}

export default QrPay
