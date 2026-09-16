import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import jsQR from 'jsqr'
import { useNavigate } from '../../routes/navigation.jsx'
import { useAuth, resolveFileUrl, hasValidBankDetails } from '../../context/AuthContext.jsx'
import { useWallet } from '../../context/WalletContext.jsx'
import { useDarkMode } from '../../hooks/useDarkMode.js'
import { RANGE_OPTIONS, formatRelativeTime, vehicleLabel } from './format.js'
import RazorpayAddMoneyModal from '../../components/Payment/RazorpayAddMoneyModal.jsx'
import WithdrawModal from '../../components/Payment/WithdrawModal.jsx'
import NFCCardOrderModal from '../../components/NFC/NFCCardOrderModal.jsx'
import NFCOrderHistoryModal from '../../components/NFC/NFCOrderHistoryModal.jsx'
import DocumentViewerModal from '../../components/Common/DocumentViewerModal.jsx'
import BankModal from '../../components/Payment/BankModal.jsx'
import './Passenger.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://api.thetapandgo.in'
function getToken() { try { return sessionStorage.getItem('tapgo_token') || '' } catch { return '' } }

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

function PassengerDocCard({ title, path, type = 'Document', onPreview }) {
  const fileUrl = resolveFileUrl(path)
  const cleanPath = (path ? path.split('?')[0].split('#')[0] : '').toLowerCase()
  const isImage = path && (
    cleanPath.endsWith('.png') ||
    cleanPath.endsWith('.jpg') ||
    cleanPath.endsWith('.jpeg') ||
    cleanPath.endsWith('.webp') ||
    cleanPath.endsWith('.gif') ||
    path.startsWith('data:image')
  )

  const fileName = (() => {
    if (!path) return ''
    try {
      const clean = path.split('?')[0].split('#')[0]
      const raw = clean.split('/').pop() || 'Document'
      return decodeURIComponent(raw)
    } catch {
      return 'Document'
    }
  })()

  const handleOpen = (e) => {
    if (onPreview && path) {
      e.preventDefault()
      onPreview({ title, path, type })
    }
  }

  return (
    <div
      style={{
        background: 'var(--card)',
        border: '1px solid var(--line)',
        borderRadius: 16,
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        minWidth: 0,
        boxSizing: 'border-box',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--muted)' }}>
            {title}
          </span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 800,
              padding: '2px 8px',
              borderRadius: 99,
              background: path ? 'rgba(31, 157, 85, 0.12)' : 'rgba(253, 211, 77, 0.14)',
              color: path ? '#1f9d55' : 'var(--yellow)',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {path ? 'Verified' : 'Missing'}
          </span>
        </div>

        {path ? (
          <div
            style={{
              marginTop: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              minWidth: 0,
              cursor: onPreview ? 'pointer' : 'default',
            }}
            onClick={handleOpen}
          >
            {isImage ? (
              <img
                src={fileUrl}
                alt={title}
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 8,
                  objectFit: 'cover',
                  border: '1px solid var(--line)',
                  flexShrink: 0,
                  background: '#f3f4f6',
                }}
              />
            ) : (
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 8,
                  background: '#f3f4f6',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Icon className="text-gray-500">description</Icon>
              </div>
            )}
            <div style={{ minWidth: 0, flex: 1 }}>
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text)',
                  display: 'block',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '100%',
                }}
                title={fileName}
              >
                {fileName}
              </span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                {isImage ? 'Image Document' : 'Document'}
              </span>
            </div>
          </div>
        ) : (
          <span style={{ display: 'block', marginTop: 8, fontSize: 14, fontWeight: 700, color: 'var(--muted)' }}>
            Not uploaded
          </span>
        )}
      </div>

      {path && (
        <a
          href={fileUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={handleOpen}
          style={{
            marginTop: 12,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            minHeight: 44,
            padding: '10px 14px',
            fontSize: 13,
            fontWeight: 800,
            color: 'var(--text)',
            background: 'var(--bg)',
            border: '1px solid var(--line)',
            borderRadius: 8,
            textDecoration: 'none',
            cursor: 'pointer',
            boxSizing: 'border-box',
            width: '100%',
          }}
        >
          <Icon style={{ fontSize: 17 }}>visibility</Icon> View {type}
        </a>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   SupportTicketModal — Create a new support ticket from the passenger dashboard
   ═══════════════════════════════════════════════════════════════════════════ */
function SupportTicketModal({ user, onClose }) {
  const [form, setFormState] = useState({ name: user?.name || '', email: user?.email || '', phone: user?.phone || '', category: 'technical', priority: 'medium', subject: '', message: '' })
  const set = (k, v) => setFormState(f => ({ ...f, [k]: v }))
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.subject.trim() || !form.message.trim()) { setError('Subject and message are required.'); return }
    setLoading(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/api/support/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (res.ok && data.success) {
        setSuccess(`Ticket #${data.ticket.id} submitted! We will reply to your email shortly.`)
      } else {
        setError(data.detail || 'Failed to submit ticket.')
      }
    } catch { setError('Service unavailable. Please try again.') } finally { setLoading(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(6px)', padding: 16 }}>
      <div style={{ width: '100%', maxWidth: 440, background: '#fff', borderRadius: 20, boxShadow: '0 20px 60px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
        <div style={{ background: '#0b1420', padding: '18px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div><div style={{ color: '#fdd34d', fontWeight: 700, fontSize: 15 }}>🎫 Contact Support</div><div style={{ color: '#8a9bad', fontSize: 12 }}>We reply within 24 hours</div></div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8a9bad', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>✕</button>
        </div>
        <div style={{ padding: '20px 20px 24px', maxHeight: '70vh', overflowY: 'auto' }}>
          {success ? (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>✅</div>
              <p style={{ fontWeight: 700, color: '#16a34a', marginBottom: 8 }}>{success}</p>
              <button onClick={onClose} style={{ marginTop: 16, padding: '10px 24px', background: '#0b1420', color: '#fdd34d', border: 'none', borderRadius: 10, fontWeight: 700, cursor: 'pointer' }}>Close</button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {error && <div style={{ padding: '10px 12px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 10, color: '#dc2626', fontSize: 13 }}>{error}</div>}
              {[['Subject', 'subject', 'text', 'Brief summary of your issue'], ['Your Name', 'name', 'text', ''], ['Email', 'email', 'email', ''], ['Phone', 'phone', 'tel', '']].map(([lbl, key, type, ph]) => (
                <label key={key} style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>{lbl}<input type={type} value={form[key]} onChange={e => set(key, e.target.value)} placeholder={ph} required style={{ display: 'block', width: '100%', marginTop: 4, padding: '9px 12px', borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 13, boxSizing: 'border-box' }} /></label>
              ))}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>Category
                  <select value={form.category} onChange={e => set('category', e.target.value)} style={{ display: 'block', width: '100%', marginTop: 4, padding: '9px 12px', borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 13 }}>
                    <option value="billing">Billing</option><option value="technical">Technical</option><option value="nfc_card">NFC Card</option><option value="account">Account</option><option value="other">Other</option>
                  </select></label>
                <label style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>Priority
                  <select value={form.priority} onChange={e => set('priority', e.target.value)} style={{ display: 'block', width: '100%', marginTop: 4, padding: '9px 12px', borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 13 }}>
                    <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option>
                  </select></label>
              </div>
              <label style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>Message
                <textarea value={form.message} onChange={e => set('message', e.target.value)} required rows={4} placeholder="Describe your issue in detail…" style={{ display: 'block', width: '100%', marginTop: 4, padding: '9px 12px', borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 13, resize: 'vertical', boxSizing: 'border-box' }} /></label>
              <button type="submit" disabled={loading} style={{ padding: '12px', background: '#0b1420', color: '#fdd34d', border: 'none', borderRadius: 10, fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}>
                {loading ? 'Submitting…' : 'Submit Support Ticket'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   NFCSecurityModal — Block / Unblock / Report Lost / Request Replacement
   ═══════════════════════════════════════════════════════════════════════════ */
function NFCSecurityModal({ user, onClose }) {
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showReplacement, setShowReplacement] = useState(false)
  const [replForm, setReplForm] = useState({ recipient_name: user?.name || '', phone: user?.phone || '', address_line1: '', area: '', city: user?.city || '', state: '', pincode: '' })
  const setRepl = (k, v) => setReplForm(f => ({ ...f, [k]: v }))

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/api/nfc/my`, { headers: { Authorization: `Bearer ${getToken()}` } })
      const data = await res.json()
      setCards(data.cards || [])
    } catch { setError('Could not load card data.') } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const card = cards[0]  // most recent card

  const doAction = async (path, body = null) => {
    setActionLoading(true); setError(''); setSuccess('')
    try {
      const res = await fetch(`${API_BASE}/api/nfc/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: body ? JSON.stringify(body) : undefined,
      })
      const data = await res.json()
      if (res.ok && data.success) { setSuccess(data.message); await load() }
      else setError(data.detail || 'Action failed.')
    } catch { setError('Service unavailable.') } finally { setActionLoading(false) }
  }

  const handleReplacement = async (e) => {
    e.preventDefault()
    await doAction('my/request-replacement', { ...replForm, card_type: card?.card_type || 'standard_nfc' })
    setShowReplacement(false)
  }

  const STATUS_COLOR = { active: '#22c55e', blocked: '#ef4444', lost: '#f59e0b', replaced: '#94a3b8' }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(6px)', padding: 16 }}>
      <div style={{ width: '100%', maxWidth: 420, background: '#fff', borderRadius: 20, boxShadow: '0 20px 60px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
        <div style={{ background: '#0b1420', padding: '18px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div><div style={{ color: '#fdd34d', fontWeight: 700, fontSize: 15 }}>💳 NFC Card Security</div><div style={{ color: '#8a9bad', fontSize: 12 }}>Manage your physical NFC card</div></div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8a9bad', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>✕</button>
        </div>
        <div style={{ padding: '20px', maxHeight: '70vh', overflowY: 'auto' }}>
          {error && <div style={{ padding: '10px 12px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 10, color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          {success && <div style={{ padding: '10px 12px', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 10, color: '#16a34a', fontSize: 13, marginBottom: 12 }}>✅ {success}</div>}
          {loading ? <p style={{ textAlign: 'center', color: '#64748b' }}>Loading card data…</p> : !card ? (
            <p style={{ textAlign: 'center', color: '#64748b', padding: '20px 0' }}>No NFC card issued to your account yet.<br />Order one from the Home screen.</p>
          ) : (
            <div>
              <div style={{ background: '#f8fafc', borderRadius: 14, padding: '16px', marginBottom: 16, border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Card Reference</div>
                <div style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 15, color: '#0b1420' }}>{card.card_reference}</div>
                <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ padding: '3px 12px', borderRadius: 20, fontSize: 12, fontWeight: 700, background: (STATUS_COLOR[card.status] || '#94a3b8') + '22', color: STATUS_COLOR[card.status] || '#94a3b8' }}>{card.status.toUpperCase()}</span>
                  <span style={{ fontSize: 12, color: '#64748b' }}>{card.card_type}</span>
                </div>
                {card.blocked_reason && <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>Reason: {card.blocked_reason}</div>}
              </div>

              {card.status === 'replaced' && <p style={{ fontSize: 13, color: '#64748b', textAlign: 'center' }}>This card has been replaced. Check your NFC Card History for the new order.</p>}

              {showReplacement ? (
                <form onSubmit={handleReplacement} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ fontWeight: 700, color: '#0b1420', marginBottom: 4 }}>Replacement Delivery Address</div>
                  {[['Recipient Name', 'recipient_name'], ['Phone', 'phone'], ['Address Line 1', 'address_line1'], ['Area / Locality', 'area'], ['City', 'city'], ['State', 'state'], ['Pincode', 'pincode']].map(([lbl, key]) => (
                    <input key={key} placeholder={lbl} value={replForm[key]} required onChange={e => setRepl(key, e.target.value)}
                      style={{ padding: '9px 12px', borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 13 }} />
                  ))}
                  <button type="submit" disabled={actionLoading} style={{ padding: 12, background: '#0b1420', color: '#fdd34d', border: 'none', borderRadius: 10, fontWeight: 700, cursor: 'pointer' }}>
                    {actionLoading ? 'Submitting…' : 'Submit Replacement Request'}
                  </button>
                  <button type="button" onClick={() => setShowReplacement(false)} style={{ padding: 10, background: '#f1f5f9', border: 'none', borderRadius: 10, fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
                </form>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {card.status === 'active' && (
                    <><button onClick={() => { if (window.confirm('Block your NFC card? You can unblock it anytime.')) doAction('my/block', { reason: 'Blocked by user from app' }) }} disabled={actionLoading}
                        style={{ padding: 12, background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 10, color: '#dc2626', fontWeight: 700, cursor: 'pointer' }}>🔒 Block Card</button>
                      <button onClick={() => { if (window.confirm('Report card as lost? This cannot be undone.')) doAction('my/report-lost') }} disabled={actionLoading}
                        style={{ padding: 12, background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 10, color: '#92400e', fontWeight: 700, cursor: 'pointer' }}>⚠️ Report Lost</button></>
                  )}
                  {card.status === 'blocked' && (
                    <><button onClick={() => doAction('my/unblock')} disabled={actionLoading}
                        style={{ padding: 12, background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 10, color: '#16a34a', fontWeight: 700, cursor: 'pointer' }}>🔓 Unblock Card</button>
                      <button onClick={() => { if (window.confirm('Report card as lost? This cannot be undone.')) doAction('my/report-lost') }} disabled={actionLoading}
                        style={{ padding: 12, background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 10, color: '#92400e', fontWeight: 700, cursor: 'pointer' }}>⚠️ Report Lost</button></>
                  )}
                  {card.status === 'lost' && (
                    <button onClick={() => setShowReplacement(true)} disabled={actionLoading}
                      style={{ padding: 12, background: '#0b1420', color: '#fdd34d', border: 'none', borderRadius: 10, fontWeight: 700, cursor: 'pointer' }}>📦 Request Replacement Card</button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
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

  // Razorpay & Withdrawal Modal State
  const [showRazorpayModal, setShowRazorpayModal] = useState(false)
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)

  // NFC Card Order Modal State
  const [showNFCOrderModal, setShowNFCOrderModal] = useState(false)
  const [showNFCHistoryModal, setShowNFCHistoryModal] = useState(false)
  // New: Support Ticket and NFC Security Modal
  const [showSupportModal, setShowSupportModal] = useState(false)
  const [showNFCSecurityModal, setShowNFCSecurityModal] = useState(false)
  const [previewDoc, setPreviewDoc] = useState(null)
  const [showBankModal, setShowBankModal] = useState(false)

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

  const handleUseExistingDetails = () => {
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
  }

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
    if (!hasValidBankDetails(user)) {
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

      <div className="wallet-note" style={{ marginBottom: 20 }}>
        <b>
          Wallet balance: ₹{balance.toFixed(2)}{' '}
          <span className="muted" style={{ fontWeight: 500, fontSize: 14 }}>
            · protected by real-time fraud detection
          </span>
        </b>
      </div>

      {!hasValidBankDetails(user) && (
        <div
          className="bank-alert-card"
          style={{
            background: 'linear-gradient(135deg, rgba(253, 211, 77, 0.14) 0%, rgba(245, 158, 11, 0.08) 100%)',
            border: '1px solid rgba(245, 158, 11, 0.45)',
            borderRadius: 16,
            padding: '16px 20px',
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 14,
            flexWrap: 'wrap',
            boxShadow: '0 4px 16px rgba(245, 158, 11, 0.08)',
          }}
        >
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 18 }}>🏦</span>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#d97706', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Payout &amp; Refund Setup</span>
            </div>
            <h3 style={{ margin: '2px 0 4px', fontSize: 16, fontWeight: 800, color: 'var(--text, #0f172a)' }}>Add Your Bank Details</h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--muted, #64748b)' }}>
              Link your bank account and UPI ID to enable seamless refunds and cashouts.
            </p>
          </div>
          <button
            type="button"
            className="primary"
            onClick={() => setShowBankModal(true)}
            style={{
              background: 'linear-gradient(135deg, #FDD34D 0%, #F59E0B 100%)',
              color: '#0f172a',
              fontWeight: 900,
              fontSize: 13,
              padding: '12px 22px',
              borderRadius: 12,
              border: 'none',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              boxShadow: '0 4px 14px rgba(245, 158, 11, 0.35)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span>Add Bank Details</span>
            <span>&rarr;</span>
          </button>
        </div>
      )}

      {/* NFC Card Ordering Banner */}
      <div style={{ background: 'linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)', borderRadius: 16, padding: '16px 20px', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <span style={{ fontSize: 11, fontWeight: 800, color: '#fde047', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Transit Hardware</span>
          <h3 style={{ margin: '2px 0 4px', fontSize: 17, color: '#fff' }}>Get Your Tap&amp;Go NFC Card</h3>
          <p style={{ margin: 0, fontSize: 13, color: '#cbd5e1' }}>Physical NFC smart card (₹50) with location-based shipping</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            onClick={() => setShowNFCHistoryModal(true)}
            style={{ padding: '8px 14px', borderRadius: 10, background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
          >
            My Orders
          </button>
          <button
            type="button"
            onClick={() => setShowNFCOrderModal(true)}
            style={{ padding: '8px 16px', borderRadius: 10, background: '#fde047', color: '#0f172a', fontSize: 12, fontWeight: 900, border: 0, cursor: 'pointer' }}
          >
            Order Card (₹50)
          </button>
        </div>
      </div>

      {/* Support & NFC Security Quick Actions */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, margin: '8px 0 4px' }}>
        <button onClick={() => setShowSupportModal(true)}
          style={{ padding: '14px 12px', background: 'linear-gradient(135deg,#1e3a5f,#0b1420)', borderRadius: 14, border: 'none', color: '#fff', textAlign: 'left', cursor: 'pointer' }}>
          <div style={{ fontSize: 20, marginBottom: 4 }}>🎫</div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>Contact Support</div>
          <div style={{ fontSize: 11, opacity: 0.7, marginTop: 2 }}>Submit a ticket</div>
        </button>
        <button onClick={() => setShowNFCSecurityModal(true)}
          style={{ padding: '14px 12px', background: 'linear-gradient(135deg,#1a2e4a,#0b1420)', borderRadius: 14, border: 'none', color: '#fff', textAlign: 'left', cursor: 'pointer' }}>
          <div style={{ fontSize: 20, marginBottom: 4 }}>💳</div>
          <div style={{ fontWeight: 700, fontSize: 13 }}>NFC Card Security</div>
          <div style={{ fontSize: 11, opacity: 0.7, marginTop: 2 }}>Block / report lost</div>
        </button>
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
                setShowRazorpayModal(true)
              }}
              disabled={isFrozen}
            >
              + Add Money
            </button>
            <button
              className="secondary-btn"
              onClick={() => {
                if (isFrozen) {
                  flash('Your wallet is frozen. Withdrawals are disabled.')
                  return
                }
                setShowWithdrawModal(true)
              }}
            >
              Withdraw to Bank
            </button>
            <button
              className="secondary-btn"
              onClick={() => setShowNFCOrderModal(true)}
              style={{ background: '#1e1b4b', color: '#fde047', border: '1px solid #312e81', fontWeight: 800 }}
            >
              Order NFC Card (₹50)
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
                setShowRazorpayModal(true)
              }}
              disabled={isFrozen}
            >
              Add Funds
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

      {/* Tap&Go Gateway-Neutral Payment Architecture Guide */}
      <div style={{
        marginTop: 28,
        borderRadius: 24,
        overflow: 'hidden',
        background: 'var(--card)',
        border: '1px solid rgba(99,102,241,0.18)',
        boxShadow: '0 8px 40px rgba(16,34,51,0.10)',
      }}>
        {/* Header */}
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
              }}>PAYMENT ARCHITECTURE</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 900, color: '#fff', letterSpacing: '-0.01em' }}>
              Tap&amp;Go Wallet Payment Workflow
            </div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', marginTop: 2, fontWeight: 600 }}>
              External payment gateways fund the wallet. Normal ride payments move directly from passenger wallet to driver wallet.
            </div>
          </div>
        </div>

        {/* Gold accent bar */}
        <div style={{ height: 3, background: 'linear-gradient(90deg,#FDD34D,#f59e0b,#6366f1)' }} />

        <div style={{ padding: '28px 28px 24px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))',
            gap: 16,
            marginBottom: 20,
          }}>
            {[
              ['1️⃣ Add Money', 'Payment Gateway → Tap&Go Wallet', 'Fund your passenger wallet using any supported payment gateway.'],
              ['2️⃣ Pay for Ride', 'Passenger Wallet → Driver Wallet', 'Tap NFC card or scan QR. Fares transfer instantly between wallets.'],
              ['3️⃣ Driver Payout', 'Tap&Go Wallet → Supported Withdrawal', 'Drivers withdraw earned wallet funds to their linked account.'],
            ].map(([title, subtitle, desc]) => (
              <div key={title} style={{
                padding: 16, borderRadius: 16, border: '1px solid var(--line)', background: 'rgba(255,255,255,0.03)'
              }}>
                <div style={{ fontWeight: 800, fontSize: 14, color: 'var(--text)', marginBottom: 4 }}>{title}</div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase', marginBottom: 6 }}>{subtitle}</div>
                <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <h2>Recent transactions</h2>
      {recentTxns.map(renderTxnRow)}
    </>
  )


  const isBankLocked = hasValidBankDetails(user) && Boolean(user?.bank_locked)

  const saveProfile = async () => {
    const bankDetails = {
      bank_account_holder: form.bank_account_holder.trim(),
      bank_account_number: form.bank_account_number.trim(),
      bank_ifsc: form.bank_ifsc.trim(),
      bank_upi_id: form.bank_upi_id.trim(),
    }
    const hasBankProposal = Object.values(bankDetails).some(Boolean)
    if (!isBankLocked && hasBankProposal && !Object.values(bankDetails).every(Boolean)) {
      flash('Provide all bank details before saving.')
      return
    }
    if (isBankLocked && hasBankProposal) {
      if (!Object.values(bankDetails).every(Boolean)) {
        flash('Provide all bank details for administrator review.')
        return
      }
      const request = await requestAdminAccess('bank', bankDetails)
      if (!request.success) {
        flash(request.message || 'Failed to submit bank-details change request.')
        return
      }
    }

    const res = await saveProfileToDb({
      name: form.name.trim() ? form.name.trim() : user?.name,
      email: form.email.trim() ? form.email.trim() : user?.email,
      address: form.address.trim() ? form.address.trim() : user?.address,
      city: form.city.trim() ? form.city.trim() : user?.city,
      emergency_contact_name: form.emergency_contact_name.trim() ? form.emergency_contact_name.trim() : user?.emergency_contact_name,
      emergency_contact_phone: form.emergency_contact_phone.trim() ? form.emergency_contact_phone.trim() : user?.emergency_contact_phone,
      ...(!isBankLocked && {
        bank_account_holder: bankDetails.bank_account_holder || user?.bank_account_holder,
        bank_account_number: bankDetails.bank_account_number || user?.bank_account_number,
        bank_ifsc: bankDetails.bank_ifsc || user?.bank_ifsc,
        bank_upi_id: bankDetails.bank_upi_id || user?.bank_upi_id,
      }),
    })
    if (res.success) {
      await refreshProfile()
      setEditing(false)
      setForm({
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
      flash(hasBankProposal && isBankLocked ? 'Bank-details change submitted for administrator approval.' : 'Profile updated in database.')
    } else {
      flash(res.message || 'Failed to save profile.')
    }
  }

  const handleToggleEdit = () => {
    if (editing) {
      saveProfile()
    } else {
      setForm({
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
      setEditing(true)
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
    setShowBankModal(true)
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {editing && (
            <>
              <button
                type="button"
                className="secondary-btn"
                style={{ padding: '6px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer', background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)', borderRadius: 8 }}
                onClick={handleUseExistingDetails}
              >
                Use existing details
              </button>
              <button
                type="button"
                className="secondary-btn"
                style={{ padding: '6px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer', background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line)', borderRadius: 8 }}
                onClick={() => setEditing(false)}
              >
                Cancel
              </button>
            </>
          )}
          <button className="back" onClick={handleToggleEdit}>
            {editing ? 'Save changes' : 'Edit details'}
          </button>
        </div>
      </div>

      <div className="field-grid">
        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Full Name</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Enter full name" autoComplete="off" /> : <span className="field-value">{user?.name || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Mobile Number</span>
            <span className="field-tag readonly">Read-only (Taken from DB)</span>
          </div>
          <span className="field-value">{user?.phone || '—'}</span>
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Email</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.email} onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} placeholder="Enter email address" autoComplete="off" /> : <span className="field-value">{user?.email || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Address</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.address} onChange={(e) => setForm(f => ({ ...f, address: e.target.value }))} placeholder="Enter address" autoComplete="off" /> : <span className="field-value">{user?.address || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">City</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.city} onChange={(e) => setForm(f => ({ ...f, city: e.target.value }))} placeholder="Enter city" autoComplete="off" /> : <span className="field-value">{user?.city || '—'}</span>}
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
          {editing ? <input value={form.emergency_contact_name} onChange={(e) => setForm(f => ({ ...f, emergency_contact_name: e.target.value }))} placeholder="Parent / Spouse Name" autoComplete="off" /> : <span className="field-value">{user?.emergency_contact_name || '—'}</span>}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Contact Phone</span>
            <span className="field-tag editable">Editable</span>
          </div>
          {editing ? <input value={form.emergency_contact_phone} onChange={(e) => setForm(f => ({ ...f, emergency_contact_phone: e.target.value }))} placeholder="10-digit mobile" autoComplete="off" /> : <span className="field-value">{user?.emergency_contact_phone || '—'}</span>}
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 28, marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Bank &amp; Refund Details</h2>
        {!hasValidBankDetails(user) ? (
          <button
            type="button"
            className="secondary-btn"
            style={{
              padding: '8px 16px',
              fontSize: 13,
              fontWeight: 800,
              color: '#0f172a',
              background: 'linear-gradient(135deg, #FDD34D 0%, #F59E0B 100%)',
              border: 'none',
              borderRadius: 10,
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(245, 158, 11, 0.25)',
            }}
            onClick={() => setShowBankModal(true)}
          >
            Add Bank Details
          </button>
        ) : isBankLocked && (
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
          {editing ? (
            <input value={form.bank_account_holder} onChange={(e) => setForm(f => ({ ...f, bank_account_holder: e.target.value }))} placeholder="Account Holder Name" autoComplete="off" />
          ) : (
            <span className="field-value">{user?.bank_account_holder || '—'}</span>
          )}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">Account Number</span>
            <span className={`field-tag ${!isBankLocked || user?.bank_request_status === 'approved' ? 'editable' : 'readonly'}`}>
              {!isBankLocked || user?.bank_request_status === 'approved' ? 'Editable' : 'Locked'}
            </span>
          </div>
          {editing ? (
            <input value={form.bank_account_number} onChange={(e) => setForm(f => ({ ...f, bank_account_number: e.target.value }))} placeholder="Bank Account Number" autoComplete="off" />
          ) : (
            <span className="field-value">
              {user?.bank_account_number
                ? user.bank_account_number.length > 4
                  ? `XXXX XXXX ${user.bank_account_number.slice(-4)}`
                  : user.bank_account_number
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
          {editing ? (
            <input value={form.bank_ifsc} onChange={(e) => setForm(f => ({ ...f, bank_ifsc: e.target.value }))} placeholder="IFSC Code (e.g. SBIN0001234)" autoComplete="off" />
          ) : (
            <span className="field-value">{user?.bank_ifsc || '—'}</span>
          )}
        </div>

        <div className="field-card">
          <div className="field-top">
            <span className="field-label">UPI ID</span>
            <span className={`field-tag ${!isBankLocked || user?.bank_request_status === 'approved' ? 'editable' : 'readonly'}`}>
              {!isBankLocked || user?.bank_request_status === 'approved' ? 'Editable' : 'Locked'}
            </span>
          </div>
          {editing ? (
            <input value={form.bank_upi_id} onChange={(e) => setForm(f => ({ ...f, bank_upi_id: e.target.value }))} placeholder="name@upi" autoComplete="off" />
          ) : (
            <span className="field-value">{user?.bank_upi_id || '—'}</span>
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
                {requestingBank ? 'Sending Request...' : 'Request Bank Details Change'}
              </button>
            </div>
          )}
        </div>
      )}

      <h2>Uploaded Verification Documents</h2>
      <div className="field-grid">
        <PassengerDocCard title="Profile Photo" path={user?.profile_photo} type="Image" onPreview={setPreviewDoc} />
        <PassengerDocCard title="Govt ID / Aadhaar / PAN" path={user?.id_document} type="Document" onPreview={setPreviewDoc} />
        <PassengerDocCard title="Digital Signature" path={user?.signature_document} type="Signature" onPreview={setPreviewDoc} />
        {user?.rc_document && <PassengerDocCard title="RC Book Document" path={user?.rc_document} type="Document" onPreview={setPreviewDoc} />}
        {user?.licence_document && <PassengerDocCard title="Driving Licence Document" path={user?.licence_document} type="Document" onPreview={setPreviewDoc} />}
        {user?.insurance_document && <PassengerDocCard title="Insurance Document" path={user?.insurance_document} type="Document" onPreview={setPreviewDoc} />}
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





      {showRazorpayModal && (
        <RazorpayAddMoneyModal
          user={user}
          onClose={() => setShowRazorpayModal(false)}
          onSuccess={async (newBalance) => {
            flash(`Wallet credited successfully! Current Balance: ₹${Number(newBalance || 0).toFixed(2)}`)
            await refreshWallet?.()
          }}
        />
      )}

      {showWithdrawModal && (
        <WithdrawModal
          user={user}
          balance={balance}
          onClose={() => setShowWithdrawModal(false)}
          onSuccess={async () => {
            flash('Withdrawal request submitted successfully.')
            await refreshWallet?.()
          }}
        />
      )}

      {showNFCOrderModal && (
        <NFCCardOrderModal
          user={user}
          onClose={() => setShowNFCOrderModal(false)}
          onOrderSuccess={() => {
            flash('NFC Card order created!')
          }}
        />
      )}

      {showNFCHistoryModal && (
        <NFCOrderHistoryModal
          user={user}
          onClose={() => setShowNFCHistoryModal(false)}
          onOrderAgain={() => setShowNFCOrderModal(true)}
        />
      )}

      {showSupportModal && (
        <SupportTicketModal user={user} onClose={() => setShowSupportModal(false)} />
      )}

      {showNFCSecurityModal && (
        <NFCSecurityModal user={user} onClose={() => setShowNFCSecurityModal(false)} />
      )}

      {previewDoc && (
        <DocumentViewerModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
      )}

      {showBankModal && (
        <BankModal
          onClose={() => setShowBankModal(false)}
          flash={flash}
          title="Bank & Refund Details"
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
