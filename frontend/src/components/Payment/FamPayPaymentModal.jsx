import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import logoImg from '../../assets/images/logio.png'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://tap-go-backend.onrender.com'


export function FamPayPaymentModal({ paymentRequest, onClose, onSuccess, flash }) {
  const { payment_request_id, upi_uri, amount } = paymentRequest
  const [status, setStatus] = useState('Pending')
  const [secondsLeft, setSecondsLeft] = useState(30)
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState('')
  const canvasRef = useRef(null)

  // Render 100% REAL Scannable QR Code with Tap&Go Logo in Center
  useEffect(() => {
    if (!canvasRef.current || !upi_uri) return

    const canvas = canvasRef.current

    QRCode.toCanvas(
      canvas,
      upi_uri,
      {
        width: 260,
        margin: 2,
        color: {
          dark: '#000000',
          light: '#ffffff',
        },
        errorCorrectionLevel: 'H',
      },
      (err) => {
        if (err) {
          console.error('QR code generation error:', err)
          return
        }

        // Overlay center Tap&Go logo badge
        const ctx = canvas.getContext('2d')
        if (!ctx) return

        const img = new Image()
        img.src = logoImg
        img.onload = () => {
          const size = canvas.width
          const badgeSize = Math.floor(size * 0.20)
          const badgeX = (size - badgeSize) / 2
          const badgeY = (size - badgeSize) / 2

          ctx.save()
          ctx.fillStyle = '#ffffff'
          ctx.shadowColor = 'rgba(0, 0, 0, 0.25)'
          ctx.shadowBlur = 4

          const r = 6
          ctx.beginPath()
          ctx.moveTo(badgeX + r, badgeY)
          ctx.lineTo(badgeX + badgeSize - r, badgeY)
          ctx.arcTo(badgeX + badgeSize, badgeY, badgeX + badgeSize, badgeY + r, r)
          ctx.lineTo(badgeX + badgeSize, badgeY + badgeSize - r)
          ctx.arcTo(badgeX + badgeSize, badgeY + badgeSize, badgeX + badgeSize - r, badgeY + badgeSize, r)
          ctx.lineTo(badgeX + r, badgeY + badgeSize)
          ctx.arcTo(badgeX, badgeY + badgeSize, badgeX, badgeY + badgeSize - r, r)
          ctx.lineTo(badgeX, badgeY + r)
          ctx.arcTo(badgeX, badgeY, badgeX + r, badgeY, r)
          ctx.closePath()
          ctx.fill()

          ctx.shadowBlur = 0
          ctx.strokeStyle = '#cbd5e1'
          ctx.lineWidth = 1.5
          ctx.stroke()

          const pad = 2
          ctx.drawImage(img, badgeX + pad, badgeY + pad, badgeSize - pad * 2, badgeSize - pad * 2)
          ctx.restore()
        }
      }
    )
  }, [upi_uri])

  // Countdown timer
  useEffect(() => {
    if (secondsLeft <= 0 || status === 'Completed') return
    const timer = setInterval(() => {
      setSecondsLeft((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [secondsLeft, status])

  // Automatic status polling every 5 seconds
  useEffect(() => {
    if (status === 'Completed') return

    const pollStatus = async () => {
      try {
        setChecking(true)
        const res = await fetch(`${API_BASE}/api/payment/status/${payment_request_id}`)
        const data = await res.json()
        setChecking(false)

        if (data.status === 'Completed' || (data.success && data.status === 'Completed')) {
          setStatus('Completed')
          setMessage(data.message || `₹${amount.toFixed(2)} added successfully!`)
          setTimeout(() => {
            onSuccess(data)
          }, 1500)
        } else if (data.message && status !== 'Completed') {
          setMessage(data.message)
        }
      } catch {
        setChecking(false)
      }
    }

    pollStatus()
    const interval = setInterval(pollStatus, 5000)
    return () => clearInterval(interval)
  }, [payment_request_id, amount, status, onSuccess])

  // Manual "I Have Paid" check
  const handleCheckNow = async () => {
    try {
      setChecking(true)
      setMessage('Verifying payment notification...')
      const res = await fetch(`${API_BASE}/api/payment/check-now/${payment_request_id}`, {
        method: 'POST',
      })
      const data = await res.json()
      setChecking(false)

      if (data.status === 'Completed' || (data.success && data.status === 'Completed')) {
        setStatus('Completed')
        setMessage(data.message || `₹${amount.toFixed(2)} added successfully!`)
        setTimeout(() => {
          onSuccess(data)
        }, 1500)
      } else {
        setMessage(data.message || 'Payment notification email not found yet. Please make sure payment was completed in FamPay/UPI app.')
        if (flash) flash(data.message || 'Payment not detected yet.')
      }
    } catch {
      setChecking(false)
      setMessage('Server error while checking payment status.')
    }
  }

  return (
    <div className="modal-overlay" style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)', zIndex: 9999 }}>
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: 440,
          width: '92%',
          borderRadius: 24,
          padding: '24px 28px',
          background: 'var(--card)',
          color: 'var(--text)',
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.35)',
          textAlign: 'center',
          border: '1px solid var(--line)',
        }}
      >
        {/* Brand Header with Logo Image */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img
              src={logoImg}
              alt="Tap&Go Logo"
              style={{ height: 32, width: 'auto', objectFit: 'contain' }}
            />
            <span style={{ fontSize: 12, fontWeight: 700, background: 'rgba(255,255,255,0.08)', padding: '4px 10px', borderRadius: 8, border: '1px solid var(--line)' }}>
              FamPay Test
            </span>
          </div>
          {status !== 'Completed' && (
            <button
              onClick={() => {
                if (window.confirm('Payment is pending. Are you sure you want to cancel?')) {
                  onClose()
                }
              }}
              style={{ border: 'none', background: 'transparent', color: 'var(--muted)', fontSize: 22, cursor: 'pointer', padding: 4, lineHeight: 1 }}
            >
              ✕
            </button>
          )}
        </div>

        {status === 'Completed' ? (
          <div style={{ padding: '24px 0' }}>
            <div style={{ fontSize: 60, color: '#1f9d55', marginBottom: 12 }}>✓</div>
            <h2 style={{ margin: '0 0 8px', fontSize: 24, color: 'var(--text)', fontWeight: 800 }}>Payment Verified!</h2>
            <p style={{ fontSize: 20, fontWeight: 900, color: '#1f9d55', margin: '0 0 12px' }}>₹{amount.toFixed(2)} added to wallet</p>
            <p className="muted" style={{ fontSize: 13 }}>
              Redirecting back to your wallet...
            </p>
          </div>
        ) : (
          <>
            <p className="eyebrow" style={{ margin: 0, textTransform: 'uppercase', letterSpacing: 1.2, fontSize: 11, fontWeight: 700, color: 'var(--yellow)' }}>
              Scan QR to Recharge Wallet
            </p>
            <h2 style={{ margin: '4px 0 20px', fontSize: 36, fontWeight: 900, color: 'var(--text)', letterSpacing: -0.5 }}>₹{amount.toFixed(2)}</h2>

            {/* Premium Scannable QR Code Container */}
            <div
              style={{
                background: '#ffffff',
                padding: 16,
                borderRadius: 24,
                display: 'inline-block',
                boxShadow: '0 12px 32px rgba(0,0,0,0.18)',
                marginBottom: 20,
                border: '1px solid #f1f5f9',
              }}
            >
              <canvas ref={canvasRef} style={{ width: 230, height: 230, display: 'block', borderRadius: 8 }} />
              <div style={{ color: '#0f172a', marginTop: 10, fontWeight: 800, fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <span>Scan with FamPay or any UPI App</span>
              </div>
            </div>

            {/* Live Status & Timer Card */}
            <div style={{ marginBottom: 20, padding: '14px 16px', borderRadius: 14, background: 'rgba(255,255,255,0.03)', border: '1px solid var(--line)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 4 }}>
                <span className="pulse-dot" style={{ width: 9, height: 9, borderRadius: '50%', background: checking ? '#f59e0b' : '#3b82f6', display: 'inline-block' }} />
                <span style={{ fontWeight: 800, fontSize: 14 }}>{checking ? 'Checking payment with Gmail...' : 'Waiting for payment...'}</span>
              </div>
              {secondsLeft > 0 ? (
                <div style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 600 }}>Checking automatically ({secondsLeft}s)</div>
              ) : (
                <div style={{ fontSize: 12, color: '#f59e0b', fontWeight: 700 }}>If already paid, click below to verify immediately</div>
              )}
            </div>

            {message && (
              <p style={{ fontSize: 12, color: message.includes('added') ? '#1f9d55' : 'var(--muted)', marginBottom: 16, fontWeight: 600 }}>{message}</p>
            )}

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                type="button"
                className="secondary-btn"
                style={{ flex: 1, padding: '14px', borderRadius: 12, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', fontWeight: 700, cursor: 'pointer', fontSize: 14 }}
                onClick={() => {
                  if (window.confirm('Cancel payment request?')) onClose()
                }}
                disabled={checking}
              >
                Cancel
              </button>

              <button
                type="button"
                className="primary"
                style={{ flex: 1.5, padding: '14px', borderRadius: 12, fontWeight: 800, cursor: 'pointer', fontSize: 14 }}
                onClick={handleCheckNow}
                disabled={checking}
              >
                {checking ? 'Verifying...' : 'I Have Paid'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
export default FamPayPaymentModal
