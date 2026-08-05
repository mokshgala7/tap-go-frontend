import { useState, useEffect } from 'react'
import { useAuth, resolveFileUrl } from '../../context/AuthContext.jsx'
import { useDriverData } from '../../context/DriverContext.jsx'
import DemoInfoCard from '../../components/Common/DemoInfoCard.jsx'
import { inr } from './format.js'

const Icon = ({ children, className = '' }) => (
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">
    {children}
  </span>
)

function FieldCard({ label, value, editable, editing, onChange, placeholder, lockedReason }) {
  return (
    <div className="field-card">
      <div className="field-top">
        <span className="field-label">{label}</span>
        <span className={`field-tag ${editable && editing ? 'editable' : 'readonly'}`}>
          {editable ? (lockedReason ? lockedReason : 'Editable') : 'Read-only'}
        </span>
      </div>
      {editable && editing ? (
        <input value={value} placeholder={placeholder || label} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <span className="field-value">{value || '\u2014'}</span>
      )}
    </div>
  )
}

function DocCard({ title, path, type = 'Document' }) {
  const fileUrl = resolveFileUrl(path)
  const isImage = path && (path.endsWith('.png') || path.endsWith('.jpg') || path.endsWith('.jpeg') || path.endsWith('.webp') || path.startsWith('data:image'))

  return (
    <div className="field-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        <div className="field-top">
          <span className="field-label">{title}</span>
          <span className={`field-tag ${path ? 'editable' : 'readonly'}`}>
            {path ? 'Verified' : 'Missing'}
          </span>
        </div>
        {path ? (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
            {isImage ? (
              <img
                src={fileUrl}
                alt={title}
                style={{ width: 44, height: 44, borderRadius: 8, objectFit: 'cover', border: '1px solid var(--line)' }}
              />
            ) : (
              <div style={{ width: 44, height: 44, borderRadius: 8, background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyCenter: 'center' }}>
                <Icon className="text-gray-500">description</Icon>
              </div>
            )}
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', wordBreak: 'break-all' }}>
              {path.split('/').pop()}
            </span>
          </div>
        ) : (
          <span className="field-value" style={{ marginTop: 4 }}>Not uploaded</span>
        )}
      </div>

      {path && (
        <a
          href={fileUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            marginTop: 12,
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
          <Icon style={{ fontSize: 16 }}>visibility</Icon> View Document
        </a>
      )}
    </div>
  )
}

function DriverAccount({ flash, dark, setDark, notifications, setNotifications, onLogout }) {
  const { user, saveProfileToDb, requestAdminAccess, refreshProfile } = useAuth()
  const { walletBalance } = useDriverData()

  const [editing, setEditing] = useState(false)
  const [requestingBank, setRequestingBank] = useState(false)
  const [requestingDoc, setRequestingDoc] = useState(false)
  const [requestingPhone, setRequestingPhone] = useState(false)

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
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key) => (value) => setForm((current) => ({ ...current, [key]: value }))

  const isBankLocked = Boolean(user?.bank_locked || user?.bank_account_number)

  const save = async () => {
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
      flash('Account & profile details updated in database.')
    } else {
      flash(res.message || 'Failed to save profile.')
    }
  }

  const handleAdminPhoneRequest = async () => {
    setRequestingPhone(true)
    const res = await requestAdminAccess('phone')
    setRequestingPhone(false)
    if (res.success) {
      flash('Admin access requested for phone number update.')
    } else {
      flash(res.message || 'Failed to send request.')
    }
  }

  const handleAdminBankRequest = async () => {
    setRequestingBank(true)
    const res = await requestAdminAccess('bank')
    setRequestingBank(false)
    if (res.success) {
      flash('Admin access requested for bank details update.')
    } else {
      flash(res.message || 'Failed to send request.')
    }
  }

  const handleAdminDocRequest = async () => {
    setRequestingDoc(true)
    const res = await requestAdminAccess('documents')
    setRequestingDoc(false)
    if (res.success) {
      flash('Admin access requested for document update.')
    } else {
      flash(res.message || 'Failed to send request.')
    }
  }

  const initials = (user?.name || 'Driver')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  const registeredOn = user?.created_at
    ? new Date(user.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
    : 'Jul 2026'

  return (
    <>
      <div className="profile">
        {user?.photoUrl ? (
          <img src={user.photoUrl} alt="" style={{ width: 56, height: 56, borderRadius: '50%', objectFit: 'cover' }} />
        ) : (
          <b>{initials}</b>
        )}
        <div>
          <h1>{user?.name || 'Driver'}</h1>
          <span>
            Driver &middot; {user?.vehicle_type || 'Vehicle'} {user?.vehicle_registration ? `\u00b7 ${user.vehicle_registration}` : ''}
          </span>
        </div>
      </div>

      <div className="wallet-note" style={{ marginTop: 20 }}>
        <b>Wallet balance: {inr(walletBalance)}</b>
        <p className="muted" style={{ margin: '4px 0 0' }}>Manage payouts from the Dashboard or Earnings tab.</p>
      </div>

      <div className="section-head" style={{ marginTop: 34 }}>
        <h2 style={{ margin: 0 }}>Personal &amp; Contact</h2>
        <button className="back" onClick={() => (editing ? save() : setEditing(true))}>
          {editing ? 'Save changes' : 'Edit details'}
        </button>
      </div>
      <div className="field-grid">
        <FieldCard label="Full Name" value={form.name} editable editing={editing} onChange={set('name')} />
        <FieldCard label="Mobile Number" value={form.phone} editable={false} />
        <FieldCard label="Email" value={form.email} editable editing={editing} onChange={set('email')} />
        <FieldCard label="Address" value={form.address} editable editing={editing} onChange={set('address')} />
        <FieldCard label="City" value={form.city} editable editing={editing} onChange={set('city')} />
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
        <FieldCard
          label="Contact Name"
          value={form.emergency_contact_name}
          editable
          editing={editing}
          onChange={set('emergency_contact_name')}
          placeholder="e.g. Parent / Spouse Name"
        />
        <FieldCard
          label="Contact Phone"
          value={form.emergency_contact_phone}
          editable
          editing={editing}
          onChange={set('emergency_contact_phone')}
          placeholder="10-digit mobile"
        />
      </div>

      <div className="section-head" style={{ marginTop: 34 }}>
        <h2 style={{ margin: 0 }}>Bank &amp; Payout Details</h2>
        {isBankLocked && (
          <span className="field-tag readonly" style={{ background: user?.bank_request_status === 'approved' ? '#dff4e8' : user?.bank_request_status === 'rejected' ? '#fde7eb' : '#FFF3C4', color: user?.bank_request_status === 'approved' ? '#1f9d55' : user?.bank_request_status === 'rejected' ? '#9f1730' : '#906500' }}>
            {user?.bank_request_status === 'approved'
              ? 'Admin Approval Granted (Editable Once)'
              : user?.bank_request_status === 'requested'
              ? 'Request Pending Admin Review'
              : user?.bank_request_status === 'rejected'
              ? 'Request Rejected'
              : 'Locked (Editable Once)'}
          </span>
        )}
      </div>

      <div className="field-grid" style={{ marginTop: 12 }}>
        <FieldCard
          label="Account Holder"
          value={form.bank_account_holder}
          editable={!isBankLocked || user?.bank_request_status === 'approved'}
          editing={editing}
          onChange={set('bank_account_holder')}
        />
        <FieldCard
          label="Account Number"
          value={form.bank_account_number ? (form.bank_account_number.length > 4 ? `XXXX XXXX ${form.bank_account_number.slice(-4)}` : form.bank_account_number) : ''}
          editable={!isBankLocked || user?.bank_request_status === 'approved'}
          editing={editing}
          onChange={set('bank_account_number')}
        />
        <FieldCard
          label="IFSC Code"
          value={form.bank_ifsc}
          editable={!isBankLocked || user?.bank_request_status === 'approved'}
          editing={editing}
          onChange={set('bank_ifsc')}
        />
        <FieldCard
          label="UPI ID"
          value={form.bank_upi_id}
          editable={!isBankLocked || user?.bank_request_status === 'approved'}
          editing={editing}
          onChange={set('bank_upi_id')}
          placeholder="name@upi"
        />
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
        <DocCard title="Profile Photo" path={user?.profile_photo} type="Image" />
        <DocCard title="Govt ID / Aadhaar / PAN" path={user?.id_document} type="Document" />
        <DocCard title="Digital Signature" path={user?.signature_document} type="Signature" />
        <DocCard title="RC Book Document" path={user?.rc_document} type="Document" />
        <DocCard title="Driving Licence Document" path={user?.licence_document} type="Document" />
        <DocCard title="Insurance Document" path={user?.insurance_document} type="Document" />
      </div>

      <div style={{ marginTop: 14 }}>
        <DemoInfoCard type="documents" />
      </div>

      <div style={{ marginTop: 12 }}>
        {user?.doc_request_status === 'requested' ? (
          <p className="muted" style={{ fontWeight: 700, color: '#d97706' }}>
            ⏳ Document re-upload request submitted to Admin.
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

      <h2>Vehicle &amp; Verification</h2>
      <div className="field-grid">
        <FieldCard label="Vehicle Number" value={user?.vehicle_registration} editable={false} />
        <FieldCard label="Vehicle Type" value={user?.vehicle_type} editable={false} />
        <FieldCard label="Vehicle Make &amp; Model" value={`${user?.vehicle_make || ''} ${user?.vehicle_model || ''}`.trim() || '—'} editable={false} />
        <FieldCard label="Driving Licence Number" value={user?.driving_licence_number} editable={false} />
      </div>

      <h2>Account Status</h2>
      <div className="field-grid">
        <FieldCard label="Driver ID" value={user?.id ? `T&G-${user.id}` : '—'} editable={false} />
        <FieldCard label="Registration Date" value={registeredOn} editable={false} />
        <FieldCard label="KYC Status" value="Verified" editable={false} />
        <FieldCard
          label="Aadhaar Verification"
          value={user?.aadhaar ? `Verified (XXXX XXXX ${user.aadhaar.slice(-4)})` : 'Pending Verification'}
          editable={false}
        />
      </div>

      <h2>Settings</h2>
      <div className="setting">
        <span>
          Notifications
          <small>Trip and payout updates</small>
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

      <button className="signout" onClick={onLogout}>
        <Icon>logout</Icon>
        Sign Out
      </button>
    </>
  )
}

export default DriverAccount
