import React, { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://tap-go-backend.onrender.com'

function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (window.Razorpay) {
      resolve(true)
      return
    }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

export function RazorpayAddMoneyModal({ user, onClose, onSuccess }) {
  const [amount, setAmount] = useState(250)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [statusMessage, setStatusMessage] = useState('')

  const PRESET_AMOUNTS = [100, 250, 500, 1000]

  const handleInitiatePayment = async (e) => {
    e?.preventDefault()
    const numAmount = Number(amount)
    if (!numAmount || numAmount < 1) {
      setError('Please enter a valid amount of at least ₹1.00')
      return
    }

    setLoading(true)
    setError('')
    setStatusMessage('Loading Razorpay secure payment gateway...')

    const resScript = await loadRazorpayScript()
    if (!resScript) {
      setError('Failed to load Razorpay Payment Gateway. Please check your internet connection.')
      setLoading(false)
      setStatusMessage('')
      return
    }

    try {
      setStatusMessage('Creating secure payment order...')
      const orderRes = await fetch(`${API_BASE}/api/payment/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.id,
          amount: numAmount,
        }),
      })

      const orderData = await orderRes.json()

      if (!orderRes.ok || !orderData.success) {
        throw new Error(orderData.detail || 'Failed to create payment order.')
      }

      const { order_id, amount: paiseAmount, currency, key_id, is_mock } = orderData

      // If key_id is not set in backend env, fallback to public key env or prompt message
      const publicKey = key_id && key_id !== 'rzp_test_placeholder' 
        ? key_id 
        : (import.meta.env.VITE_RAZORPAY_KEY_ID || 'rzp_test_placeholder')

      setStatusMessage('Opening Razorpay checkout...')

      const options = {
        key: publicKey,
        amount: paiseAmount,
        currency: currency || 'INR',
        name: 'Tap & Go',
        description: `Wallet Top-up (₹${numAmount.toFixed(2)})`,
        order_id: order_id,
        prefill: {
          name: user.name || '',
          email: user.email || '',
          contact: user.phone || '',
        },
        theme: {
          color: '#0b1420',
        },
        modal: {
          ondismiss: function () {
            setLoading(false)
            setStatusMessage('')
            setError('Payment checkout cancelled.')
          },
        },
        handler: async function (response) {
          setStatusMessage('Verifying payment signature with server...')
          try {
            const verifyRes = await fetch(`${API_BASE}/api/payment/verify-payment`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                user_id: user.id,
                razorpay_order_id: response.razorpay_order_id || order_id,
                razorpay_payment_id: response.razorpay_payment_id || `pay_mock_${Date.now()}`,
                razorpay_signature: response.razorpay_signature || `sig_mock_${Date.now()}`,
                amount: numAmount,
              }),
            })

            const verifyData = await verifyRes.json()

            if (verifyRes.ok && verifyData.success) {
              setStatusMessage('Payment verified! Crediting wallet...')
              await onSuccess?.(verifyData.balance)
              setTimeout(() => {
                onClose?.()
              }, 1000)
            } else {
              throw new Error(verifyData.detail || verifyData.message || 'Payment verification failed.')
            }
          } catch (vErr) {
            setError(vErr.message || 'Verification failed.')
            setLoading(false)
            setStatusMessage('')
          }
        },
      }

      const rzp = new window.Razorpay(options)
      rzp.on('payment.failed', function (resp) {
        setError(resp.error?.description || 'Payment failed. Please try again.')
        setLoading(false)
        setStatusMessage('')
      })
      rzp.open()
    } catch (err) {
      setError(err.message || 'Could not launch payment.')
      setLoading(false)
      setStatusMessage('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200">
        {/* Header */}
        <div className="bg-slate-900 text-white p-5 flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-yellow-400 text-black flex items-center justify-center font-bold text-sm">
              ₹
            </span>
            <div>
              <h3 className="font-bold text-base">Add Money to Wallet</h3>
              <p className="text-xs text-slate-400">Powered by Razorpay Standard Checkout</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="text-slate-400 hover:text-white transition-colors p-1 text-lg font-bold"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {error && (
            <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-semibold flex items-center gap-2">
              <span className="text-base">⚠️</span>
              <span>{error}</span>
            </div>
          )}

          {statusMessage && !error && (
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-2">
              <span className="inline-block w-4 h-4 border-2 border-slate-800 border-t-transparent rounded-full animate-spin"></span>
              <span>{statusMessage}</span>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
              Select or Enter Amount (₹)
            </label>
            <div className="grid grid-cols-4 gap-2 mb-3">
              {PRESET_AMOUNTS.map((amt) => (
                <button
                  key={amt}
                  type="button"
                  onClick={() => setAmount(amt)}
                  className={`py-2 text-xs font-bold rounded-xl border transition-all ${
                    amount === amt
                      ? 'bg-slate-900 text-yellow-400 border-slate-900 shadow'
                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  +₹{amt}
                </button>
              ))}
            </div>

            <div className="relative">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 font-bold text-base">
                ₹
              </span>
              <input
                type="number"
                min="1"
                step="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="Enter amount"
                disabled={loading}
                className="w-full pl-8 pr-4 py-3 rounded-xl border border-slate-300 focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 font-bold text-lg text-slate-900 outline-none transition-all"
              />
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200 text-xs text-slate-600 space-y-1">
            <div className="flex justify-between">
              <span>Top-up Amount:</span>
              <strong className="text-slate-900">₹{Number(amount || 0).toFixed(2)}</strong>
            </div>
            <div className="flex justify-between">
              <span>Payment Gateway Fee:</span>
              <strong className="text-emerald-600 font-bold">FREE (₹0.00)</strong>
            </div>
            <div className="flex justify-between border-t border-slate-200 pt-1.5 font-bold text-slate-900 text-sm">
              <span>Total Payable:</span>
              <span>₹{Number(amount || 0).toFixed(2)}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleInitiatePayment}
            disabled={loading}
            className="w-full py-3.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-yellow-400 font-bold text-sm transition-all shadow-lg flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {loading ? (
              <>
                <span className="inline-block w-4 h-4 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin"></span>
                Processing...
              </>
            ) : (
              <>
                <span>Proceed to Secure Checkout</span>
                <span>→</span>
              </>
            )}
          </button>

          <p className="text-[11px] text-center text-slate-400">
            🔒 256-Bit SSL Encrypted Razorpay Checkout
          </p>
        </div>
      </div>
    </div>
  )
}

export default RazorpayAddMoneyModal
