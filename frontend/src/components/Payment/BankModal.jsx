import React, { useState } from 'react'
import { useAuth, hasValidBankDetails } from '../../context/AuthContext.jsx'

export default function BankModal({ onClose, flash, title = 'Bank Account & Payout Details' }) {
  const { user, saveProfileToDb, requestAdminAccess, refreshProfile } = useAuth()
  const [requesting, setRequesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isLocked = hasValidBankDetails(user) && Boolean(user?.bank_locked) && user?.bank_request_status !== 'approved'

  const [form, setForm] = useState({
    accountHolder: user?.bank_account_holder || '',
    accountNumber: user?.bank_account_number || '',
    ifsc: user?.bank_ifsc || '',
    upiId: user?.bank_upi_id || '',
  })

  const update = (key) => (e) => {
    setError('')
    setForm((current) => ({ ...current, [key]: e.target.value }))
  }

  const validate = () => {
    const holder = form.accountHolder.trim()
    const number = form.accountNumber.trim()
    const ifsc = form.ifsc.trim().toUpperCase()
    const upi = form.upiId.trim()

    if (!holder) {
      setError('Account Holder Name is required.')
      return false
    }
    if (holder.length < 2) {
      setError('Please enter a valid Account Holder Name.')
      return false
    }
    if (!number) {
      setError('Bank Account Number is required.')
      return false
    }
    if (!/^\d{8,20}$/.test(number)) {
      setError('Enter a valid Bank Account Number (8-20 digits).')
      return false
    }
    if (!ifsc) {
      setError('IFSC Code is required.')
      return false
    }
    if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc)) {
      setError('Enter a valid 11-character IFSC code (e.g. SBIN0001234).')
      return false
    }
    if (!upi) {
      setError('UPI ID is required.')
      return false
    }
    if (!/^[a-zA-Z0-9.\-_]{2,49}@[a-zA-Z]{2,49}$/.test(upi)) {
      setError('Enter a valid UPI ID (e.g. name@upi).')
      return false
    }
    return true
  }

  const handleSave = async (e) => {
    e?.preventDefault()
    if (!validate()) return

    setSaving(true)
    setError('')

    const payload = {
      bank_account_holder: form.accountHolder.trim(),
      bank_account_number: form.accountNumber.trim(),
      bank_ifsc: form.ifsc.trim().toUpperCase(),
      bank_upi_id: form.upiId.trim(),
    }

    try {
      const res = await saveProfileToDb(payload)
      setSaving(false)

      if (res.success) {
        await refreshProfile()
        onClose()
        flash?.('Bank account details saved & locked in database.')
      } else {
        setError(res.message || 'Failed to save bank details.')
      }
    } catch {
      setSaving(false)
      setError('Failed to connect to server. Please try again.')
    }
  }

  const handleRequestAccess = async (e) => {
    e?.preventDefault()
    if (!validate()) return

    setRequesting(true)
    setError('')

    try {
      const res = await requestAdminAccess('bank', {
        bank_account_holder: form.accountHolder.trim(),
        bank_account_number: form.accountNumber.trim(),
        bank_ifsc: form.ifsc.trim().toUpperCase(),
        bank_upi_id: form.upiId.trim(),
      })
      setRequesting(false)

      if (res.success) {
        await refreshProfile()
        onClose()
        flash?.('Admin access requested for editing bank account.')
      } else {
        setError(res.message || 'Request failed.')
      }
    } catch {
      setRequesting(false)
      setError('Failed to submit change request. Please try again.')
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.55)',
        backdropFilter: 'blur(6px)',
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 460,
          background: 'var(--card, #ffffff)',
          color: 'var(--text, #111827)',
          borderRadius: 20,
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          overflow: 'hidden',
          border: '1px solid var(--line, #e5e7eb)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            background: 'var(--header-bg, #0b1420)',
            padding: '18px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          <div>
            <div style={{ color: '#fdd34d', fontWeight: 800, fontSize: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>🏦</span> {title}
            </div>
            <div style={{ color: '#8a9bad', fontSize: 12, marginTop: 2 }}>
              {isLocked ? 'Locked for security · Admin approval required' : 'Add your permanent bank payout details'}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#8a9bad',
              fontSize: 22,
              cursor: 'pointer',
              lineHeight: 1,
              padding: 4,
            }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div style={{ padding: '20px 22px 24px', maxHeight: '75vh', overflowY: 'auto' }}>
          <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--muted, #6b7280)', lineHeight: 1.5 }}>
            {isLocked
              ? '🔒 Your bank details are permanently stored and locked. Submitting new details will send a request to administrators for review.'
              : 'Details saved here will be stored permanently in the database. Note: Bank details are verified and locked after the initial save.'}
          </p>

          {error && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 10,
                background: '#fde7eb',
                color: '#9f1730',
                fontSize: 13,
                fontWeight: 600,
                marginBottom: 14,
              }}
            >
              ⚠️ {error}
            </div>
          )}

          <form onSubmit={isLocked ? handleRequestAccess : handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text, #374151)', marginBottom: 6 }}>
                Account Holder Name <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                value={form.accountHolder}
                onChange={update('accountHolder')}
                placeholder="e.g. Full Name as in Bank Passbook"
                autoComplete="off"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: '1px solid var(--line, #d1d5db)',
                  background: 'var(--bg, #f9fafb)',
                  color: 'var(--text, #111827)',
                  fontSize: 14,
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text, #374151)', marginBottom: 6 }}>
                Bank Account Number <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                value={form.accountNumber}
                onChange={update('accountNumber')}
                placeholder="Bank Account Number (digits only)"
                autoComplete="off"
                inputMode="numeric"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: '1px solid var(--line, #d1d5db)',
                  background: 'var(--bg, #f9fafb)',
                  color: 'var(--text, #111827)',
                  fontSize: 14,
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text, #374151)', marginBottom: 6 }}>
                IFSC Code <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                value={form.ifsc}
                onChange={update('ifsc')}
                placeholder="e.g. SBIN0001234 or HDFC0001234"
                autoComplete="off"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: '1px solid var(--line, #d1d5db)',
                  background: 'var(--bg, #f9fafb)',
                  color: 'var(--text, #111827)',
                  fontSize: 14,
                  textTransform: 'uppercase',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text, #374151)', marginBottom: 6 }}>
                UPI ID <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                value={form.upiId}
                onChange={update('upiId')}
                placeholder="e.g. username@okhdfcbank or name@upi"
                autoComplete="off"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: '1px solid var(--line, #d1d5db)',
                  background: 'var(--bg, #f9fafb)',
                  color: 'var(--text, #111827)',
                  fontSize: 14,
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
              {isLocked ? (
                user?.bank_request_status === 'requested' ? (
                  <p style={{ fontWeight: 700, color: '#d97706', textAlign: 'center', margin: 0, fontSize: 13 }}>
                    ⏳ Admin access request pending approval.
                  </p>
                ) : (
                  <button
                    type="submit"
                    disabled={requesting}
                    style={{
                      width: '100%',
                      padding: '12px 16px',
                      borderRadius: 12,
                      background: '#f59e0b',
                      color: '#111',
                      border: 'none',
                      fontWeight: 800,
                      fontSize: 14,
                      cursor: requesting ? 'not-allowed' : 'pointer',
                      opacity: requesting ? 0.7 : 1,
                    }}
                  >
                    {requesting ? 'Submitting Request...' : 'Submit Changes for Admin Approval'}
                  </button>
                )
              ) : (
                <button
                  type="submit"
                  disabled={saving || !form.accountHolder?.trim() || !form.accountNumber?.trim() || !form.ifsc?.trim() || !form.upiId?.trim()}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    borderRadius: 12,
                    background: (form.accountHolder?.trim() && form.accountNumber?.trim() && form.ifsc?.trim() && form.upiId?.trim())
                      ? 'linear-gradient(135deg, #FDD34D 0%, #F59E0B 100%)'
                      : 'var(--line, #e2e8f0)',
                    color: (form.accountHolder?.trim() && form.accountNumber?.trim() && form.ifsc?.trim() && form.upiId?.trim())
                      ? '#0f172a'
                      : 'var(--muted, #94a3b8)',
                    border: 'none',
                    fontWeight: 800,
                    fontSize: 14,
                    cursor: saving || !form.accountHolder?.trim() || !form.accountNumber?.trim() || !form.ifsc?.trim() || !form.upiId?.trim() ? 'not-allowed' : 'pointer',
                    opacity: saving ? 0.7 : 1,
                    boxShadow: (form.accountHolder?.trim() && form.accountNumber?.trim() && form.ifsc?.trim() && form.upiId?.trim())
                      ? '0 4px 14px rgba(245, 158, 11, 0.3)'
                      : 'none',
                    transition: 'all 0.2s ease',
                  }}
                >
                  {saving ? 'Saving to Database...' : 'Save & Lock Bank Account'}
                </button>
              )}

              <button
                type="button"
                onClick={onClose}
                style={{
                  width: '100%',
                  padding: '10px 16px',
                  borderRadius: 12,
                  background: 'transparent',
                  color: 'var(--text, #374151)',
                  border: '1px solid var(--line, #d1d5db)',
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
