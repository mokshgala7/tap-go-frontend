import { useEffect, useMemo, useRef, useState } from 'react'
import jsQR from 'jsqr'
import { useNavigate } from '../../routes/navigation.jsx'
import { useAuth, resolveFileUrl } from '../../context/AuthContext.jsx'
import { useWallet } from '../../context/WalletContext.jsx'
import { useDarkMode } from '../../hooks/useDarkMode.js'
import { RANGE_OPTIONS, formatRelativeTime, vehicleLabel } from './format.js'
import FamPayPaymentModal from '../../components/Payment/FamPayPaymentModal.jsx'
import './Passenger.css'

const Icon = ({ children, className = '' }) => (
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">
    {children}
  </span>
)

const QUICK_AMOUNTS = [100, 200, 500, 1000]

// Demo trip a scanned QR (or the manual fallback) resolves to until a real
// POS machine + backend exist.
const DEMO_TRIP = {
  driver: 'Ramesh Kumar',
  vehicleType: 'Auto',
  vehicleNumber: 'DL 3C AB 4521',
  fare: 58,
}

function PassengerDocCard({ title, path }) {
  const fileUrl = resolveFileUrl(path)
  const isImage = path && (path.endsWith('.png') || path.endsWith('.jpg') || path.endsWith('.jpeg') || path.endsWith('.webp') || path.startsWith('data:image'))

  return (
    <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 16, padding: 14, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--muted)' }}>{title}</span>
          <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 8px', borderRadius: 99, background: path ? 'rgba(31, 157, 85, 0.12)' : 'rgba(253, 211, 77, 0.14)', color: path ? '#1f9d55' : 'var(--yellow)' }}>
            {path ? 'Verified' : 'Missing'}
          </span>
        </div>
        {path ? (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
            {isImage ? (
              <img src={fileUrl} alt={title} style={{ width: 40, height: 40, borderRadius: 8, objectFit: 'cover', border: '1px solid var(--line)' }} />
            ) : (
              <div style={{ width: 40, height: 40, borderRadius: 8, background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyCenter: 'center' }}>
                <Icon className="text-gray-500">description</Icon>
              </div>
            )}
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', wordBreak: 'break-all' }}>{path.split('/').pop()}</span>
          </div>
        ) : (
          <span style={{ display: 'block', marginTop: 6, fontSize: 14, fontWeight: 700 }}>Not uploaded</span>
        )}
      </div>
      {path && (
        <a
          href={fileUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            marginTop: 10,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 800,
            color: 'var(--text)',
            background: 'var(--bg)',
            border: '1px solid var(--line)',
            borderRadius: 8,
            textDecoration: 'none',
            cursor: 'pointer',
          }}
        >
          <Icon style={{ fontSize: 15 }}>visibility</Icon> View File
        </a>
      )}
    </div>
  )
}

function Passenger() {
  const navigate = useNavigate()
  const { user, logout, saveProfileToDb, requestAdminAccess, refreshProfile } = useAuth()
  const { balance, isFrozen, transactions, addMoney, withdraw, payFare } = useWallet()

  const [tab, setTabState] = useState(() => {
    return sessionStorage.getItem('passenger_tab') || 'home'
  })

  const setTab = (newTab) => {
    setTabState(newTab)
    try {
      sessionStorage.setItem('passenger_tab', newTab)
    } catch {
      // Ignore storage error
    }
  }
  const [notice, setNotice] = useState('')
  const [dark, setDark] = useDarkMode()
  const [notifications, setNotifications] = useState(true)
  const [range, setRange] = useState('1M')
  const [amountInput, setAmountInput] = useState('')
  const [editing, setEditing] = useState(false)
  const [requestingBank, setRequestingBank] = useState(false)
  const [requestingDoc, setRequestingDoc] = useState(false)
  const [requestingPhone, setRequestingPhone] = useState(false)

  // Withdrawal Modal State
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [withdrawLoading, setWithdrawLoading] = useState(false)

  // Top-up Modal State
  const [showTopupModal, setShowTopupModal] = useState(false)
  const [topupModalAmount, setTopupModalAmount] = useState('')
  const [topupLoading, setTopupLoading] = useState(false)
  const [activePaymentRequest, setActivePaymentRequest] = useState(null)

  const handleInitiateFamPay = async (amt) => {
    if (!amt || amt <= 0) {
      flash('Please enter a valid top-up amount.')
      return
    }
    setTopupLoading(true)
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'https://tap-go-backend.onrender.com'}/api/payment/create-request`, {

        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, amount: amt, payment_method: 'fampay' }),
      })
      const data = await res.json()
      setTopupLoading(false)
      if (res.ok && data.success) {
        setShowTopupModal(false)
        setActivePaymentRequest(data)
      } else {
        flash(data.detail || 'Could not create payment request.')
      }
    } catch {
      setTopupLoading(false)
      flash('Backend error creating payment request.')
    }
  }

  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    city: '',
    emergency_contact_name: '',
    emergency_contact_phone: '',
    bank_account_holder: '',
    bank_account_number: '',
    bank_ifsc: '',
    bank_upi_id: '',
  })

  useEffect(() => {
    if (user) {
      setForm({
        name: user.name || '',
        email: user.email || '',
        phone: user.phone || '',
        address: user.address || '',
        city: user.city || '',
        emergency_contact_name: user.emergency_contact_name || '',
        emergency_contact_phone: user.emergency_contact_phone || '',
        bank_account_holder: user.bank_account_holder || '',
        bank_account_number: user.bank_account_number || '',
        bank_ifsc: user.bank_ifsc || '',
        bank_upi_id: user.bank_upi_id || '',
      })
    }
  }, [user])

  useEffect(() => {
    if (user?.id) {
      refreshProfile()
    }
  }, [tab]) // eslint-disable-line react-hooks/exhaustive-deps

  const video = useRef(null)
  const canvasRef = useRef(null)
  const stream = useRef(null)
  const rafRef = useRef(null)
  const [cameraError, setCameraError] = useState('')

  const stopScanner = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
  }

  useEffect(() => {
    if (!user) navigate('/login')
  }, [user, navigate])

  useEffect(() => () => stopScanner(), []) // eslint-disable-line react-hooks/exhaustive-deps

  const flash = (message) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 3200)
  }

  const goHome = () => navigate('/')

  const tickScan = () => {
    const v = video.current
    const canvas = canvasRef.current
    if (v && canvas && v.readyState === v.HAVE_ENOUGH_DATA) {
      canvas.width = v.videoWidth
      canvas.height = v.videoHeight
      const ctx = canvas.getContext('2d')
      ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const code = jsQR(imageData.data, imageData.width, imageData.height)
      if (code) {
        completeQrPayment()
        return
      }
    }
    rafRef.current = requestAnimationFrame(tickScan)
  }

  const openScanner = async () => {
    setTab('scan')
    setCameraError('')
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      })
      if (video.current) {
        video.current.srcObject = stream.current
        await video.current.play()
      }
      rafRef.current = requestAnimationFrame(tickScan)
    } catch {
      setCameraError('Camera permission is needed to scan a QR code.')
    }
  }

  const backFromScanner = () => {
    stopScanner()
    setTab('home')
  }

  const completeQrPayment = async () => {
    stopScanner()
    const res = await payFare({ ...DEMO_TRIP, method: 'QR' })
    setTab('home')
    if (res.success) {
      flash(`Paid ₹${res.fare} via QR.`)
    } else {
      flash(res.message || 'Payment failed.')
    }
  }

  const handleTapToPay = () => {
    flash('Tap your card on the driver\u2019s machine to pay.')
  }

  const handleAddMoney = async (amount) => {
    if (!amount || amount <= 0) {
      flash('Please enter a valid top-up amount.')
      return
    }
    const res = await addMoney(amount)
    if (res.success) {
      setAmountInput('')
      flash(res.message || `₹${amount} added to your wallet.`)
    } else {
      flash(res.message || 'Top-up failed.')
    }
  }

  const handleWithdrawSubmit = async (e) => {
    e.preventDefault()
    const num = Number(withdrawAmount)
    if (!num || num <= 0) {
      flash('Enter a valid amount to withdraw.')
      return
    }
    if (num > balance) {
      flash(`Cannot withdraw more than available balance (₹${balance.toFixed(2)}).`)
      return
    }
    if (!user?.bank_account_number) {
      flash('Please save your bank details in Profile first.')
      return
    }
    if (isFrozen) {
      flash('Your wallet is frozen. Withdrawals are disabled.')
      return
    }

    setWithdrawLoading(true)
    const res = await withdraw(num)
    setWithdrawLoading(false)

    if (res.success) {
      setShowWithdrawModal(false)
      setWithdrawAmount('')
      flash(res.message || 'Withdrawal to bank account successful.')
    } else {
      flash(res.message || 'Withdrawal failed.')
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const rangeMsValue = RANGE_OPTIONS.find((r) => r.key === range)?.ms ?? Infinity
  const filteredTxns = useMemo(
    () => transactions.filter((t) => Date.now() - t.timestamp <= rangeMsValue),
    [transactions, rangeMsValue],
  )

  if (!user) return null
  const recentTxns = transactions.slice(0, 4)
  const initials = (user?.name || 'Passenger')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  const renderTxnRow = (t) => {
    const isCredit = t.raw ? t.raw.is_credit : (t.is_credit !== undefined ? t.is_credit : t.fare < 0)
    const typeText = t.raw ? t.raw.type : (t.type || (isCredit ? 'Deposit' : 'Trip Payment'))
    const descText = t.raw ? t.raw.description : (t.description || (isCredit ? `₹${Math.abs(t.amount || t.fare).toFixed(2)} credited to wallet` : `₹${Math.abs(t.amount || t.fare).toFixed(2)} paid to ${t.driver || 'Driver'}`))
    const balAfter = t.raw ? t.raw.balance_after : (t.balance_after !== undefined ? t.balance_after : null)
    const methodText = t.raw ? t.raw.payment_method : (t.method || t.payment_method || 'WALLET')
    const refText = t.raw ? t.raw.reference : (t.reference || t.id)
    const dateText = t.raw && t.raw.created_at ? new Date(t.raw.created_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : formatRelativeTime(t.timestamp)

    return (
      <article className="ride" key={t.id || t.reference} style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6, padding: '14px 16px', marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <b style={{ fontSize: 15, color: 'var(--text)' }}>{typeText}</b>
            <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 8, padding: '2px 8px', borderRadius: 99, background: isCredit ? '#dff4e8' : '#fde7eb', color: isCredit ? '#1f9d55' : '#9f1730' }}>
              {isCredit ? 'CREDIT' : 'DEBIT'}
            </span>
          </div>
          <strong className={isCredit ? 'credit' : ''} style={{ fontSize: 16, color: isCredit ? '#1f9d55' : 'var(--text)' }}>
            {isCredit ? '+' : '-'}₹{Math.abs(t.amount || t.fare).toFixed(2)}
          </strong>
        </div>

        <div style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 600 }}>
          {descText}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4, pt: 6, borderTop: '1px dashed var(--line)', fontSize: 12 }}>
          <span style={{ fontWeight: 700, color: 'var(--text)' }}>
            Available balance: ₹{balAfter !== null && balAfter !== undefined ? Number(balAfter).toFixed(2) : balance.toFixed(2)}
          </span>
          <span className="muted" style={{ fontSize: 11 }}>
            {refText} &middot; {methodText} &middot; {dateText}
          </span>
        </div>
      </article>
    )
  }

  const home = (
    <>
      <p className="eyebrow">Welcome back</p>
      <h1>Hi, {(user?.name || 'Passenger').split(' ')[0]} 👋</h1>
      <p className="muted">Choose a quick, cashless way to pay your driver.</p>

      <div className="payments">
        <button onClick={handleTapToPay}>
          <Icon>contactless</Icon>
          <b>Tap &amp; Pay</b>
          <small>Tap your card at the driver&apos;s machine</small>
        </button>
        <button onClick={openScanner}>
          <Icon>qr_code_scanner</Icon>
          <b>Scan QR</b>
          <small>Scan your driver&apos;s QR code</small>
        </button>
      </div>

      <div className="wallet-note" style={{ marginBottom: 30 }}>
        <b>
          Wallet balance: ₹{balance.toFixed(2)}{' '}
          <span className="muted" style={{ fontWeight: 500, fontSize: 14 }}>
            · protected by real-time fraud detection
          </span>
        </b>
      </div>

      <h2>Transaction History</h2>
      {transactions.length > 0 ? (
        transactions.slice(0, 5).map(renderTxnRow)
      ) : (
        <p className="muted" style={{ padding: '20px 0', textAlign: 'center' }}>No transactions yet.</p>
      )}
    </>
  )

  const activity = (
    <>
      <h1>Activity</h1>
      <p className="muted">All your rides and wallet transactions</p>
      <div className="ranges">
        {RANGE_OPTIONS.map((option) => (
          <button
            key={option.key}
            className={range === option.key ? 'active' : ''}
            onClick={() => setRange(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {filteredTxns.length ? filteredTxns.map(renderTxnRow) : <p className="muted">No transactions in this range yet.</p>}
    </>
  )

  const wallet = (
    <>
      <h1>My Wallet</h1>
      <p className="muted">Add money or withdraw your Tap&amp;Go balance to bank.</p>
      
      {isFrozen && (
        <div style={{ background: '#fde7eb', border: '1px solid #f998a6', color: '#9f1730', padding: '12px 16px', borderRadius: 12, marginBottom: 16, fontWeight: 700, fontSize: 14 }}>
          ⚠️ Your wallet is frozen by an administrator. Adding funds and withdrawals are currently disabled.
        </div>
      )}

      <div className="wallet-grid" style={{ marginTop: 20 }}>
        <div className="wallet">
          <span>
            Tap<span>&amp;</span>Go Wallet
          </span>
          <small>Available balance</small>
          <b>₹{balance.toFixed(2)}</b>
          <div className="wallet-actions">
            <button
              className="primary"
              onClick={() => {
                if (isFrozen) {
                  flash('Your wallet is frozen. Adding funds is disabled.')
                  return
                }
                setTopupModalAmount(amountInput ? String(amountInput) : '')
                setShowTopupModal(true)
              }}
              disabled={isFrozen}
            >
              + Add Money
            </button>
            <button
              className="secondary-btn"
              onClick={() => {
                if (!user?.bank_account_number) {
                  flash('Please save your bank details in Profile first.')
                  return
                }
                if (balance <= 0) {
                  flash('Available wallet balance is ₹0.00.')
                  return
                }
                if (isFrozen) {
                  flash('Your wallet is frozen. Withdrawals are disabled.')
                  return
                }
                setWithdrawAmount(String(balance))
                setShowWithdrawModal(true)
              }}
            >
              Withdraw to Bank
            </button>
          </div>
        </div>

        <div className="wallet-note">
          <b>Add money</b>
          <p className="muted" style={{ margin: '0 0 14px' }}>
            Instant wallet top-up backed by MySQL database.
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {QUICK_AMOUNTS.map((value) => (
              <button
                key={value}
                onClick={() => setAmountInput(String(value))}
                style={{
                  border: '1px solid var(--line)',
                  borderRadius: 10,
                  padding: '8px 14px',
                  background: amountInput === String(value) ? 'var(--yellow)' : 'var(--card)',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                ₹{value}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <input
              type="number"
              min="1"
              placeholder="Custom amount"
              value={amountInput}
              onChange={(e) => setAmountInput(e.target.value)}
              style={{
                flex: 1,
                border: '1px solid var(--line)',
                borderRadius: 10,
                padding: '10px 14px',
                background: 'var(--bg)',
                color: 'var(--text)',
                fontSize: 16,
              }}
            />
            <button
              className="primary"
              onClick={() => {
                const amt = Number(amountInput)
                if (!amt || amt <= 0) {
                  flash('Please enter how much you want to add.')
                  return
                }
                handleInitiateFamPay(amt)
              }}
              disabled={isFrozen || topupLoading}
            >
              {topupLoading ? 'Loading...' : 'Add'}
            </button>
          </div>
        </div>
      </div>

      <div className="wallet-note" style={{ marginTop: 20 }}>
        <b>How wallet payments work</b>
        <p className="muted" style={{ margin: 0 }}>
          Fares move wallet-to-wallet: your balance goes down and the driver&apos;s goes up instantly. All transactions are recorded in MySQL.
        </p>
      </div>

      {/* Always show the PayU review workflow details */}
      {true && (
        <div style={{
          marginTop: 28,
          borderRadius: 24,
          overflow: 'hidden',
          background: 'var(--card)',
          border: '1px solid rgba(99,102,241,0.18)',
          boxShadow: '0 8px 40px rgba(16,34,51,0.10)',
        }}>
          {/* ── Header ─────────────────────────────────────────────────── */}
          <div style={{
            background: 'linear-gradient(135deg,#1C1C2E 0%,#2d2d4e 100%)',
            padding: '22px 28px',
            display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12,
              background: 'linear-gradient(135deg,#6366f1,#8b5cf6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 22, flexShrink: 0,
            }}>💳</div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{
                  padding: '2px 10px', borderRadius: 20,
                  background: 'linear-gradient(90deg,#6366f1,#8b5cf6)',
                  color: '#fff', fontSize: 10, fontWeight: 900, letterSpacing: '0.15em',
                }}>PAYU REVIEW TEAM</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 900, color: '#fff', letterSpacing: '-0.01em' }}>
                Current Payment Workflow (Demo)
              </div>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', marginTop: 2, fontWeight: 600 }}>
                This project uses a temporary FamPay-based payment workflow for demonstration purposes while awaiting PayU merchant onboarding.
              </div>
            </div>
          </div>

          {/* Gold accent bar */}
          <div style={{ height: 3, background: 'linear-gradient(90deg,#FDD34D,#f59e0b,#6366f1)' }} />

          <div style={{ padding: '28px 28px 24px' }}>

            {/* ── Stepper Row ─────────────────────────────────────────── */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))',
              gap: 20,
              marginBottom: 28,
            }}>

              {/* Current Workflow Stepper */}
              <div style={{
                borderRadius: 18, overflow: 'hidden',
                border: '1.5px solid rgba(245,158,11,0.25)',
                background: 'rgba(245,158,11,0.03)',
              }}>
                <div style={{
                  padding: '14px 18px',
                  background: 'linear-gradient(90deg,rgba(245,158,11,0.12),rgba(245,158,11,0.04))',
                  borderBottom: '1px solid rgba(245,158,11,0.18)',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <span style={{ fontSize: 16 }}>🟡</span>
                  <span style={{ fontSize: 12, fontWeight: 900, color: '#b45309', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Current Demo Workflow</span>
                </div>
                <div style={{ padding: '18px 18px 14px' }}>
                  {[
                    ['🧑‍💼', 'Passenger', '#92400e'],
                    ['📲', 'Enter Wallet Top-up Amount', 'var(--text)'],
                    ['📱', 'Dynamic UPI QR Generated', 'var(--text)'],
                    ['💸', 'Pay using any UPI App', 'var(--text)'],
                    ['🏦', 'Payment received in Tap&Go Demo Account (FamPay)', 'var(--text)'],
                    ['🔍', 'Backend verifies payment', 'var(--text)'],
                    ['✅', 'Passenger Wallet Credited', '#059669'],
                    ['📋', 'Transaction stored in Wallet History', '#059669'],
                  ].map(([icon, label, color], i, arr) => (
                    <div key={i}>
                      <div style={{
                        display: 'flex', alignItems: 'flex-start', gap: 10,
                        padding: '7px 0',
                      }}>
                        <div style={{
                          width: 32, height: 32, borderRadius: 10, flexShrink: 0,
                          background: i === 0 ? 'rgba(245,158,11,0.15)' : color.includes('059') ? 'rgba(5,150,105,0.1)' : 'rgba(0,0,0,0.04)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 15,
                        }}>{icon}</div>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color, paddingTop: 6, lineHeight: 1.4 }}>{label}</div>
                      </div>
                      {i < arr.length - 1 && (
                        <div style={{ paddingLeft: 15, color: 'rgba(245,158,11,0.5)', fontSize: 16, lineHeight: 1, userSelect: 'none' }}>│</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Future PayU Workflow Stepper */}
              <div style={{
                borderRadius: 18, overflow: 'hidden',
                border: '1.5px solid rgba(99,102,241,0.25)',
                background: 'rgba(99,102,241,0.03)',
              }}>
                <div style={{
                  padding: '14px 18px',
                  background: 'linear-gradient(90deg,rgba(99,102,241,0.12),rgba(99,102,241,0.04))',
                  borderBottom: '1px solid rgba(99,102,241,0.18)',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <span style={{ fontSize: 16 }}>🔵</span>
                  <span style={{ fontSize: 12, fontWeight: 900, color: '#4338ca', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Future PayU Workflow</span>
                </div>
                <div style={{ padding: '18px 18px 14px' }}>
                  {[
                    ['🧑‍💼', 'Passenger', '#4338ca'],
                    ['📲', 'Enter Wallet Top-up Amount', 'var(--text)'],
                    ['🏛️', 'Official PayU Checkout', '#6366f1'],
                    ['💳', 'Payment Processed by PayU', 'var(--text)'],
                    ['🔐', 'Secure Payment Success Callback', 'var(--text)'],
                    ['🔍', 'Backend Verification', 'var(--text)'],
                    ['⚡', 'Wallet Updated Instantly', '#059669'],
                    ['📋', 'Transaction Stored', '#059669'],
                    ['✅', 'Success Confirmation', '#059669'],
                  ].map(([icon, label, color], i, arr) => (
                    <div key={i}>
                      <div style={{
                        display: 'flex', alignItems: 'flex-start', gap: 10,
                        padding: '7px 0',
                      }}>
                        <div style={{
                          width: 32, height: 32, borderRadius: 10, flexShrink: 0,
                          background: i === 0 ? 'rgba(99,102,241,0.15)' : color.includes('4338') || color.includes('6366') ? 'rgba(99,102,241,0.1)' : color.includes('059') ? 'rgba(5,150,105,0.1)' : 'rgba(0,0,0,0.04)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 15,
                        }}>{icon}</div>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color, paddingTop: 6, lineHeight: 1.4 }}>{label}</div>
                      </div>
                      {i < arr.length - 1 && (
                        <div style={{ paddingLeft: 15, color: 'rgba(99,102,241,0.4)', fontSize: 16, lineHeight: 1, userSelect: 'none' }}>│</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ── Comparison Table ────────────────────────────────────── */}
            <div style={{ marginBottom: 24 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14,
              }}>
                <span style={{ fontSize: 15 }}>📊</span>
                <span style={{ fontSize: 13, fontWeight: 900, color: 'var(--text)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Feature Comparison</span>
              </div>
              <div style={{ overflowX: 'auto', borderRadius: 14, border: '1px solid var(--line)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 480 }}>
                  <thead>
                    <tr style={{ background: 'linear-gradient(90deg,rgba(99,102,241,0.08),rgba(139,92,246,0.05))' }}>
                      {['Feature', 'Current Demo', 'After PayU Integration'].map((col, i) => (
                        <th key={col} style={{
                          padding: '12px 16px', textAlign: i === 0 ? 'left' : 'center',
                          fontWeight: 900, fontSize: 11,
                          textTransform: 'uppercase', letterSpacing: '0.08em',
                          color: i === 2 ? '#4338ca' : 'var(--text)',
                          borderBottom: '1px solid var(--line)',
                          whiteSpace: 'nowrap',
                        }}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['💳 Payment Method', 'Dynamic UPI QR (FamPay Demo)', 'Official PayU Payment Gateway'],
                      ['🔐 Verification', 'Demo backend verification', 'Secure PayU Callback'],
                      ['⚡ Wallet Update', 'Automatic', 'Instant'],
                      ['📋 Transaction History', '✅ Yes', '✅ Yes'],
                      ['🛡️ Security', 'Demo Implementation', 'Production-grade PayU Security'],
                      ['🎯 Purpose', 'Evaluation & Testing', 'Live Production Payments'],
                    ].map(([feature, demo, payu], rowIndex) => (
                      <tr key={rowIndex} style={{
                        background: rowIndex % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.02)',
                        borderBottom: rowIndex < 5 ? '1px solid var(--line)' : 'none',
                      }}>
                        <td style={{ padding: '11px 16px', fontWeight: 700, color: 'var(--text)' }}>{feature}</td>
                        <td style={{ padding: '11px 16px', textAlign: 'center', color: '#b45309', fontWeight: 600 }}>{demo}</td>
                        <td style={{ padding: '11px 16px', textAlign: 'center', color: '#4338ca', fontWeight: 700 }}>{payu}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ── Important Note ──────────────────────────────────────── */}
            <div style={{
              borderRadius: 14,
              background: 'linear-gradient(135deg,rgba(251,191,36,0.1),rgba(245,158,11,0.06))',
              border: '1.5px solid rgba(251,191,36,0.35)',
              padding: '16px 20px',
              display: 'flex', gap: 14, alignItems: 'flex-start',
            }}>
              <div style={{
                width: 40, height: 40, flexShrink: 0, borderRadius: 10,
                background: 'rgba(251,191,36,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 20,
              }}>⚠️</div>
              <div>
                <div style={{ fontSize: 11, fontWeight: 900, color: '#92400e', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 5 }}>
                  Important Note for PayU Review Team
                </div>
                <div style={{ fontSize: 12.5, color: '#78350f', fontWeight: 600, lineHeight: 1.65 }}>
                  Current payment processing uses a <strong style={{ color: '#92400e' }}>temporary FamPay-based demonstration workflow</strong> developed solely for testing and evaluation purposes.
                  <br /><br />
                  Upon <strong style={{ color: '#92400e' }}>PayU merchant approval</strong>, this workflow will be <strong style={{ color: '#92400e' }}>completely replaced</strong> with the official PayU Payment Gateway — without affecting the wallet, transaction history, or user experience.
                </div>
              </div>
            </div>

          </div>
        </div>
      )}

      <h2>Recent transactions</h2>
      {recentTxns.map(renderTxnRow)}
    </>
  )


  const isBankLocked = Boolean(user?.bank_locked || user?.bank_account_number)

  const saveProfile = async () => {
    const res = await saveProfileToDb({
      name: form.name,
      email: form.email,
      address: form.address,
      city: form.city,
      emergency_contact_name: form.emergency_contact_name,
      emergency_contact_phone: form.emergency_contact_phone,
      bank_account_holder: form.bank_account_holder,
      bank_account_number: form.bank_account_number,
      bank_ifsc: form.bank_ifsc,
      bank_upi_id: form.bank_upi_id,
    })
    if (res.success) {
      setEditing(false)
      flash('Profile updated in database.')
    } else {
      flash(res.message || 'Failed to save profile.')
    }
  }

  const handleAdminPhoneRequest = async () => {
    setRequestingPhone(true)
    const res = await requestAdminAccess('phone')
    setRequestingPhone(false)
    if (res.success) flash('Admin access requested for phone number change.')
    else flash(res.message || 'Request failed.')
  }

  const handleAdminBankRequest = async () => {
    setRequestingBank(true)
    const res = await requestAdminAccess('bank')
    setRequestingBank(false)
    if (res.success) flash('Admin access requested for bank details.')
    else flash(res.message || 'Request failed.')
  }

  const handleAdminDocRequest = async () => {
    setRequestingDoc(true)
    const res = await requestAdminAccess('documents')
    setRequestingDoc(false)
    if (res.success) flash('Admin access requested for document edit.')
    else flash(res.message || 'Request failed.')
  }

  const profile = (
    <>
      <div className="profile">
        {user?.photoUrl ? (
          <img
            src={user.photoUrl}
            alt=""
            style={{ width: 56, height: 56, borderRadius: '50%', objectFit: 'cover' }}
          />
        ) : (
          <b>{initials}</b>
        )}
        <div>
          <h1>{user?.name || 'Passenger'}</h1>
          <span>Passenger · Tap&amp;Go Account</span>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 28, marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Personal &amp; Contact</h2>
        <button className="back" onClick={() => (editing ? saveProfile() : setEditing(true))}>
          {editing ? 'Save changes' : 'Edit details'}
        </button>
      </div>

      <div className="field-grid">
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Full Name</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} /> : <span className="field-value">{form.name || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Mobile Number</span>
            <span className="field-tag readonly">Read-only (Taken from DB)</span>
          </div>
          <span className="field-value">{form.phone || '—'}</span>
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Email</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.email} onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} /> : <span className="field-value">{form.email || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Address</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.address} onChange={(e) => setForm(f => ({ ...f, address: e.target.value }))} /> : <span className="field-value">{form.address || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">City</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.city} onChange={(e) => setForm(f => ({ ...f, city: e.target.value }))} /> : <span className="field-value">{form.city || '—'}</span>}
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        {user?.phone_request_status === 'requested' ? (
          <p className="muted" style={{ fontWeight: 700, color: '#d97706', margin: '6px 0 0' }}>
            ⏳ Phone number change request submitted to Admin. Awaiting authorization.
          </p>
        ) : (
          <button
            className="secondary-btn"
            style={{ color: 'var(--text)', background: 'var(--card)', border: '1px solid var(--line)' }}
            disabled={requestingPhone}
            onClick={handleAdminPhoneRequest}
          >
            {requestingPhone ? 'Sending Request...' : 'Request Admin Access to Change Phone Number'}
          </button>
        )}
      </div>

      <h2>Emergency Contact</h2>
      <div className="field-grid">
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Contact Name</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.emergency_contact_name} onChange={(e) => setForm(f => ({ ...f, emergency_contact_name: e.target.value }))} placeholder="Parent / Spouse Name" /> : <span className="field-value">{form.emergency_contact_name || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Contact Phone</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.emergency_contact_phone} onChange={(e) => setForm(f => ({ ...f, emergency_contact_phone: e.target.value }))} placeholder="10-digit mobile" /> : <span className="field-value">{form.emergency_contact_phone || '—'}</span>}
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 28, marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Bank &amp; Refund Details</h2>
        {isBankLocked && (
          <span className="field-tag readonly" style={{ background: user?.bank_request_status === 'approved' ? '#dff4e8' : user?.bank_request_status === 'rejected' ? '#fde7eb' : '#FFF3C4', color: user?.bank_request_status === 'approved' ? '#1f9d55' : user?.bank_request_status === 'rejected' ? '#9f1730' : '#906500' }}>
            {user?.bank_request_status === 'approved'
              ? 'Admin Approval Granted (Editable Once)'
              : user?.bank_request_status === 'requested'
              ? 'Request Pending Admin Review'
              : user?.bank_request_status === 'rejected'
              ? 'Request Rejected'
              : 'Locked (Saved Once)'}
          </span>
        )}
      </div>

      <div className="field-grid">
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Account Holder</span>
            <span className={`field-tag ${!isBankLocked || user?.bank_request_status === 'approved' ? 'editable' : 'readonly'}`}>
              {!isBankLocked || user?.bank_request_status === 'approved' ? 'Editable' : 'Locked'}
            </span>
          </div>
          {editing && (!isBankLocked || user?.bank_request_status === 'approved') ? (
            <input value={form.bank_account_holder} onChange={(e) => setForm(f => ({ ...f, bank_account_holder: e.target.value }))} placeholder="Account Holder Name" />
          ) : (
            <span className="field-value">{form.bank_account_holder || '—'}</span>
          )}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Account Number</span>
            <span className={`field-tag ${!isBankLocked || user?.bank_request_status === 'approved' ? 'editable' : 'readonly'}`}>
              {!isBankLocked || user?.bank_request_status === 'approved' ? 'Editable' : 'Locked'}
            </span>
          </div>
          {editing && (!isBankLocked || user?.bank_request_status === 'approved') ? (
            <input value={form.bank_account_number} onChange={(e) => setForm(f => ({ ...f, bank_account_number: e.target.value }))} placeholder="Bank Account Number" />
          ) : (
            <span className="field-value">
              {form.bank_account_number
                ? form.bank_account_number.length > 4
                  ? `XXXX XXXX ${form.bank_account_number.slice(-4)}`
                  : form.bank_account_number
                : '—'}
            </span>
          )}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">IFSC Code</span>
            <span className={`field-tag ${!isBankLocked || user?.bank_request_status === 'approved' ? 'editable' : 'readonly'}`}>
              {!isBankLocked || user?.bank_request_status === 'approved' ? 'Editable' : 'Locked'}
            </span>
          </div>
          {editing && (!isBankLocked || user?.bank_request_status === 'approved') ? (
            <input value={form.bank_ifsc} onChange={(e) => setForm(f => ({ ...f, bank_ifsc: e.target.value }))} placeholder="IFSC Code (e.g. SBIN0001234)" />
          ) : (
            <span className="field-value">{form.bank_ifsc || '—'}</span>
          )}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">UPI ID</span>
            <span className={`field-tag ${!isBankLocked || user?.bank_request_status === 'approved' ? 'editable' : 'readonly'}`}>
              {!isBankLocked || user?.bank_request_status === 'approved' ? 'Editable' : 'Locked'}
            </span>
          </div>
          {editing && (!isBankLocked || user?.bank_request_status === 'approved') ? (
            <input value={form.bank_upi_id} onChange={(e) => setForm(f => ({ ...f, bank_upi_id: e.target.value }))} placeholder="name@upi" />
          ) : (
            <span className="field-value">{form.bank_upi_id || '—'}</span>
          )}
        </div>
      </div>

      {isBankLocked && (
        <div style={{ marginTop: 12 }}>
          {user?.bank_request_status === 'requested' ? (
            <p className="muted" style={{ fontWeight: 700, color: '#d97706' }}>
              ⏳ Bank edit request submitted to Admin. Awaiting access authorization.
            </p>
          ) : user?.bank_request_status === 'approved' ? (
            <p style={{ fontWeight: 700, color: '#1f9d55' }}>
              ✅ Admin approval granted! Click &quot;Edit details&quot; above to update your bank info.
            </p>
          ) : (
            <div>
              {user?.bank_request_status === 'rejected' && (
                <p style={{ fontWeight: 700, color: '#9f1730', marginBottom: 6 }}>
                  ❌ Your previous bank edit request was rejected by Admin.
                </p>
              )}
              <button
                className="secondary-btn"
                style={{ color: 'var(--text)', background: 'var(--card)', border: '1px solid var(--line)', marginTop: 4 }}
                disabled={requestingBank}
                onClick={handleAdminBankRequest}
              >
                {requestingBank ? 'Sending Request...' : 'Request Admin Access to Edit Bank Details'}
              </button>
            </div>
          )}
        </div>
      )}

      <h2>Uploaded Verification Documents</h2>
      <div className="field-grid">
        <PassengerDocCard title="Profile Photo" path={user?.profile_photo} />
        <PassengerDocCard title="Govt ID / Aadhaar / PAN" path={user?.id_document} />
        <PassengerDocCard title="Digital Signature" path={user?.signature_document} />
      </div>

      <div style={{ marginTop: 12 }}>
        {user?.doc_request_status === 'requested' ? (
          <p className="muted" style={{ fontWeight: 700, color: '#d97706' }}>
            ⏳ Document edit request submitted to Admin.
          </p>
        ) : (
          <button
            className="secondary-btn"
            style={{ color: 'var(--text)', background: 'var(--card)', border: '1px solid var(--line)', marginTop: 8 }}
            disabled={requestingDoc}
            onClick={handleAdminDocRequest}
          >
            {requestingDoc ? 'Sending Request...' : 'Request Admin Access to Edit Documents'}
          </button>
        )}
      </div>

      <h2>Account Status</h2>
      <div className="field-grid">
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Passenger ID</span>
            <span className="field-tag readonly">Read-only</span>
          </div>
          <span className="field-value">T&amp;G-{user?.id || '—'}</span>
        </div>
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Registration Date</span>
            <span className="field-tag readonly">Read-only</span>
          </div>
          <span className="field-value">
            {user?.created_at
              ? new Date(user.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
              : 'Jul 2026'}
          </span>
        </div>
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Aadhaar Status</span>
            <span className="field-tag readonly">Read-only</span>
          </div>
          <span className="field-value">
            {user?.aadhaar ? `Verified (XXXX XXXX ${user.aadhaar.slice(-4)})` : 'Pending'}
          </span>
        </div>
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">PAN Card</span>
            <span className="field-tag readonly">Read-only</span>
          </div>
          <span className="field-value">{user?.pan || '—'}</span>
        </div>
      </div>

      <h2>Settings</h2>
      <div className="setting">
        <span>
          Notifications
          <small>Ride and payment updates</small>
        </span>
        <button className={notifications ? 'switch on' : 'switch'} onClick={() => setNotifications(!notifications)}>
          <i />
        </button>
      </div>
      <div className="setting">
        <span>
          Dark mode
          <small>Use the darker interface</small>
        </span>
        <button className={dark ? 'switch on' : 'switch'} onClick={() => setDark(!dark)}>
          <i />
        </button>
      </div>

      <button className="signout" onClick={handleLogout}>
        <Icon>logout</Icon>
        Sign Out
      </button>
    </>
  )

  const scan = (
    <>
      <button className="back" onClick={backFromScanner}>
        ← Back to home
      </button>
      <h1>Scan QR code</h1>
      <p className="muted">Point your camera at the driver&apos;s Tap&amp;Go QR code.</p>
      <div className="camera">
        {cameraError ? (
          <div className="hint">{cameraError}</div>
        ) : (
          <video ref={video} autoPlay playsInline muted />
        )}
        <canvas ref={canvasRef} style={{ display: 'none' }} />
        <div className="frame" />
      </div>
      {cameraError && (
        <button className="primary" onClick={completeQrPayment}>
          Simulate Scan (Camera Unavailable)
        </button>
      )}
    </>
  )

  const screen =
    tab === 'activity' ? activity : tab === 'wallet' ? wallet : tab === 'profile' ? profile : tab === 'scan' ? scan : home

  return (
    <div className="passenger">
      <header>
        <button className="logo" onClick={goHome} aria-label="Tap&Go home">
          Tap<span>&amp;</span>Go
        </button>
        <div className="header-actions">
          <button className="icon-btn" onClick={() => setTab('profile')} aria-label="Profile">
            {user?.photoUrl ? (
              <img
                src={user.photoUrl}
                alt=""
                style={{ width: 39, height: 39, borderRadius: '50%', objectFit: 'cover' }}
              />
            ) : (
              <span className="user">{initials}</span>
            )}
          </button>
        </div>
      </header>

      <main>{screen}</main>

      {showWithdrawModal && (
        <div className="modal-overlay" onClick={() => setShowWithdrawModal(false)}>
          <div className="modal-card" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>Withdrawal to Bank Account</h3>
              <button
                onClick={() => setShowWithdrawModal(false)}
                style={{ border: 0, background: 'var(--bg)', color: 'var(--text)', borderRadius: '50%', width: 32, height: 32, cursor: 'pointer', display: 'grid', placeItems: 'center' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleWithdrawSubmit}>
              <div style={{ background: 'var(--bg)', padding: 14, borderRadius: 12, marginBottom: 16, border: '1px solid var(--line)' }}>
                <small className="muted" style={{ fontWeight: 700, textTransform: 'uppercase' }}>AVAILABLE WALLET BALANCE</small>
                <div style={{ fontSize: 24, fontWeight: 900, color: 'var(--text)', marginTop: 2 }}>₹{balance.toFixed(2)}</div>
              </div>

              <div style={{ background: 'var(--bg)', padding: 14, borderRadius: 12, marginBottom: 16, border: '1px solid var(--line)' }}>
                <small className="muted" style={{ fontWeight: 700, textTransform: 'uppercase' }}>DESTINATION BANK ACCOUNT</small>
                <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4 }}>{user?.bank_account_holder || user?.name}</div>
                <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 2 }}>
                  A/C: XXXX XXXX {user?.bank_account_number?.slice(-4)} &middot; IFSC: {user?.bank_ifsc || '—'}
                </div>
              </div>

              <label style={{ display: 'block', fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
                Withdrawal Amount (₹)
              </label>
              <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                <input
                  type="number"
                  min="1"
                  max={balance}
                  step="any"
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                  placeholder="Enter amount"
                  required
                  style={{
                    flex: 1,
                    border: '1px solid var(--line)',
                    borderRadius: 10,
                    padding: '10px 14px',
                    background: 'var(--card)',
                    color: 'var(--text)',
                    fontSize: 16,
                  }}
                />
                <button
                  type="button"
                  onClick={() => setWithdrawAmount(String(balance))}
                  style={{
                    border: '1px solid var(--line)',
                    borderRadius: 10,
                    padding: '0 14px',
                    background: 'var(--bg)',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  Max
                </button>
              </div>

              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  type="button"
                  className="secondary-btn"
                  style={{ flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', fontWeight: 700, cursor: 'pointer' }}
                  onClick={() => setShowWithdrawModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="primary"
                  style={{ flex: 1, padding: '12px 16px', borderRadius: 10, fontWeight: 800, cursor: 'pointer' }}
                  disabled={withdrawLoading || !withdrawAmount || Number(withdrawAmount) <= 0 || Number(withdrawAmount) > balance}
                >
                  {withdrawLoading ? 'Processing...' : 'Confirm Transfer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showTopupModal && (
        <div className="modal-overlay" onClick={() => !topupLoading && setShowTopupModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <h3 style={{ margin: '0 0 8px' }}>Add Money to Wallet</h3>
            <p className="muted" style={{ margin: '0 0 16px', fontSize: 14 }}>
              Enter the exact amount you want to top up into your Tap&amp;Go wallet.
            </p>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
              {[100, 200, 500, 1000].map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setTopupModalAmount(String(val))}
                  style={{
                    border: '1px solid var(--line)',
                    borderRadius: 10,
                    padding: '8px 14px',
                    background: topupModalAmount === String(val) ? 'var(--yellow)' : 'var(--card)',
                    fontWeight: 700,
                    cursor: 'pointer',
                    color: 'var(--text)',
                  }}
                >
                  ₹{val}
                </button>
              ))}
            </div>

            <label htmlFor="topup-amount-input" style={{ fontWeight: 700, display: 'block', marginBottom: 6, fontSize: 14 }}>
              Top-up Amount (₹)
            </label>
            <input
              id="topup-amount-input"
              type="number"
              min="1"
              placeholder="Enter amount e.g. 500"
              value={topupModalAmount}
              onChange={(e) => setTopupModalAmount(e.target.value)}
              style={{
                width: '100%',
                border: '1px solid var(--line)',
                borderRadius: 10,
                padding: '12px 14px',
                fontSize: 16,
                background: 'var(--card)',
                color: 'var(--text)',
                marginBottom: 20,
                boxSizing: 'border-box',
              }}
              autoFocus
            />

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                type="button"
                className="secondary-btn"
                style={{ flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => setShowTopupModal(false)}
                disabled={topupLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="primary"
                style={{ flex: 1, padding: '12px 16px', borderRadius: 10, fontWeight: 800, cursor: 'pointer' }}
                disabled={!topupModalAmount || Number(topupModalAmount) <= 0 || topupLoading}
                onClick={async () => {
                  const amt = Number(topupModalAmount)
                  if (!amt || amt <= 0) {
                    flash('Please enter a valid top-up amount.')
                    return
                  }
                  await handleInitiateFamPay(amt)
                }}
              >
                {topupLoading ? 'Generating QR...' : topupModalAmount ? `Proceed (₹${topupModalAmount})` : 'Proceed to Pay'}
              </button>
            </div>
          </div>
        </div>
      )}

      {activePaymentRequest && (
        <FamPayPaymentModal
          paymentRequest={activePaymentRequest}
          onClose={() => setActivePaymentRequest(null)}
          onSuccess={async (res) => {
            setActivePaymentRequest(null)
            setTopupModalAmount('')
            setAmountInput('')
            flash(res.message || '₹' + (activePaymentRequest.amount || 0) + ' added successfully!')
            setTimeout(() => {
              window.location.reload()
            }, 800)
          }}
          flash={flash}
        />
      )}

      {notice && <div className="toast">✓ {notice}</div>}

      <nav>
        {[
          ['home', 'home', 'Home'],
          ['activity', 'receipt_long', 'Activity'],
          ['wallet', 'account_balance_wallet', 'Wallet'],
          ['profile', 'person', 'Profile'],
        ].map(([key, icon, label]) => (
          <button className={tab === key ? 'active' : ''} onClick={() => setTab(key)} key={key}>
            <Icon>{icon}</Icon>
            {label}
          </button>
        ))}
      </nav>
    </div>
  )
}

export default Passenger
