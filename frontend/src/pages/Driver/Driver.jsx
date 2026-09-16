import { useEffect, useState } from 'react'
import { useNavigate } from '../../routes/navigation.jsx'
import { useAuth, hasValidBankDetails } from '../../context/AuthContext.jsx'
import { useDriverData } from '../../context/DriverContext.jsx'
import { useDarkMode } from '../../hooks/useDarkMode.js'
import DriverDashboard from './DriverDashboard.jsx'
import DriverEarnings from './DriverEarnings.jsx'
import DriverAccount from './DriverAccount.jsx'
import { inr } from './format.js'
import WithdrawModal from '../../components/Payment/WithdrawModal.jsx'
import BankModal from '../../components/Payment/BankModal.jsx'
import '../Passenger/Passenger.css'
import './Driver.css'

const Icon = ({ children, className = '' }) => (
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">
    {children}
  </span>
)

function Driver() {
  const navigate = useNavigate()
  const { user, logout, refreshProfile } = useAuth()
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
    if (!user) {
      navigate('/login')
    } else if (user?.id) {
      refreshProfile()
    }
  }, [user?.id]) // eslint-disable-line react-hooks/exhaustive-deps

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
        openModal={setModal}
      />
    ) : (
      <DriverDashboard flash={flash} openModal={setModal} goToEarnings={() => setTab('earnings')} />
    )

  return (
    <div className="driver">
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
