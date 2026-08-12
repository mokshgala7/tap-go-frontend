import { useEffect, useState } from 'react'
import { useNavigate } from '../../routes/navigation.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import { useDriverData } from '../../context/DriverContext.jsx'
import { useDarkMode } from '../../hooks/useDarkMode.js'
import DriverDashboard from './DriverDashboard.jsx'
import DriverEarnings from './DriverEarnings.jsx'
import DriverAccount from './DriverAccount.jsx'
import { inr } from './format.js'
import DevBanner from '../../components/Common/DevBanner.jsx'
import WithdrawModal from '../../components/Payment/WithdrawModal.jsx'
import '../Passenger/Passenger.css'
import './Driver.css'

const Icon = ({ children, className = '' }) => (
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">
    {children}
  </span>
)



function BankModal({ onClose, flash }) {
  const { user, saveProfileToDb, requestAdminAccess } = useAuth()
  const { saveBankDetails } = useDriverData()
  const [requesting, setRequesting] = useState(false)
  const [saving, setSaving] = useState(false)

  const isLocked = Boolean(user?.bank_locked || user?.bank_account_number) && user?.bank_request_status !== 'approved'

  const [form, setForm] = useState({
    accountHolder: user?.bank_account_holder || '',
    accountNumber: user?.bank_account_number || '',
    ifsc: user?.bank_ifsc || '',
    upiId: user?.bank_upi_id || '',
  })

  useEffect(() => {
    if (user) {
      setForm({
        accountHolder: user.bank_account_holder || '',
        accountNumber: user.bank_account_number || '',
        ifsc: user.bank_ifsc || '',
        upiId: user.bank_upi_id || '',
      })
    }
  }, [user])

  const update = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }))

  const handleSave = async () => {
    setSaving(true)
    const res = await saveProfileToDb({
      bank_account_holder: form.accountHolder,
      bank_account_number: form.accountNumber,
      bank_ifsc: form.ifsc,
      bank_upi_id: form.upiId,
    })
    setSaving(false)

    if (res.success) {
      saveBankDetails(form)
      onClose()
      flash('Bank account details saved & locked in database.')
    } else {
      flash(res.message || 'Failed to save bank details.')
    }
  }

  const handleRequestAccess = async () => {
    setRequesting(true)
    const res = await requestAdminAccess('bank')
    setRequesting(false)
    if (res.success) {
      flash('Admin access requested for editing bank account.')
    } else {
      flash(res.message || 'Request failed.')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h3>Bank Account & Payout Details</h3>
        <p className="muted" style={{ marginBottom: 16 }}>
          {isLocked
            ? '🔒 Bank details are locked after initial save. You must request admin access to make further updates.'
            : 'Details saved here will be stored in your database profile. Note: Bank details can be saved/edited only ONCE before locking.'}
        </p>

        <label htmlFor="bank-holder">Account Holder Name</label>
        <input id="bank-holder" value={form.accountHolder} disabled={isLocked} onChange={update('accountHolder')} placeholder="e.g. Full Name" />

        <label htmlFor="bank-number">Account Number</label>
        <input id="bank-number" value={form.accountNumber} disabled={isLocked} onChange={update('accountNumber')} placeholder="Bank Account Number" />

        <label htmlFor="bank-ifsc">IFSC Code</label>
        <input id="bank-ifsc" value={form.ifsc} disabled={isLocked} onChange={update('ifsc')} placeholder="e.g. SBIN0001234" />

        <label htmlFor="bank-upi">UPI ID</label>
        <input id="bank-upi" value={form.upiId} disabled={isLocked} onChange={update('upiId')} placeholder="name@upi" />

        <div className="modal-actions" style={{ flexDirection: 'column', gap: 10, marginTop: 22 }}>
          {isLocked ? (
            user?.bank_request_status === 'requested' ? (
              <p className="muted" style={{ fontWeight: 700, color: '#d97706', textAlign: 'center', margin: 0 }}>
                ⏳ Admin access request pending approval.
              </p>
            ) : (
              <button className="primary" disabled={requesting} onClick={handleRequestAccess}>
                {requesting ? 'Submitting Request...' : 'Request Admin Access to Edit'}
              </button>
            )
          ) : (
            <button className="primary" disabled={saving || !form.accountNumber} onClick={handleSave}>
              {saving ? 'Saving to Database...' : 'Save & Lock Bank Account'}
            </button>
          )}

          <button className="secondary-btn" onClick={onClose} style={{ width: '100%', color: 'var(--text)', background: 'var(--bg)', border: '1px solid var(--line)' }}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function Driver() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { withdraw } = useDriverData()

  const [tab, setTabState] = useState(() => {
    return sessionStorage.getItem('driver_tab') || 'dashboard'
  })

  const setTab = (newTab) => {
    setTabState(newTab)
    try {
      sessionStorage.setItem('driver_tab', newTab)
    } catch {
      // Ignore storage error
    }
  }
  const [notice, setNotice] = useState('')
  const [dark, setDark] = useDarkMode()
  const [notifications, setNotifications] = useState(true)
  const [modal, setModal] = useState(null)

  useEffect(() => {
    if (!user) navigate('/login')
  }, [user, navigate])

  const flash = (message) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 2800)
  }

  const goHome = () => navigate('/')

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  if (!user) return null

  const initials = (user?.name || 'Driver')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  const screen =
    tab === 'earnings' ? (
      <DriverEarnings flash={flash} />
    ) : tab === 'account' ? (
      <DriverAccount
        flash={flash}
        dark={dark}
        setDark={setDark}
        notifications={notifications}
        setNotifications={setNotifications}
        onLogout={handleLogout}
      />
    ) : (
      <DriverDashboard flash={flash} openModal={setModal} goToEarnings={() => setTab('earnings')} />
    )

  return (
    <div className="driver">
      <DevBanner />
      <header>
        <button className="logo" onClick={goHome} aria-label="Tap&Go home">
          Tap<span>&amp;</span>Go
        </button>
        <div className="header-actions">
          <button className="icon-btn" onClick={() => setTab('account')} aria-label="Account">
            {user?.photoUrl ? (
              <img src={user.photoUrl} alt="" style={{ width: 39, height: 39, borderRadius: '50%', objectFit: 'cover' }} />
            ) : (
              <span className="user">{initials}</span>
            )}
          </button>
        </div>
      </header>

      <main>{screen}</main>

      {notice && <div className="toast">✓ {notice}</div>}

      <nav>
        {[
          ['dashboard', 'dashboard', 'Dashboard'],
          ['earnings', 'payments', 'Earnings'],
          ['account', 'person', 'Account'],
        ].map(([key, icon, label]) => (
          <button className={tab === key ? 'active' : ''} onClick={() => setTab(key)} key={key}>
            <Icon>{icon}</Icon>
            {label}
          </button>
        ))}
      </nav>

      {modal === 'withdraw' && (
        <WithdrawModal
          user={user}
          balance={user?.wallet?.balance || 0}
          onClose={() => setModal(null)}
          onSuccess={async () => {
            flash('Withdrawal request submitted.')
          }}
        />
      )}

      {modal === 'bank' && (
        <BankModal
          onClose={() => setModal(null)}
          flash={flash}
        />
      )}
    </div>
  )
}

export default Driver
