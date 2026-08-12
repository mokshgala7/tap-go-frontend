import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'
import { Link } from '../routes/navigation.jsx'

export function PaymentInfo() {
  const steps = [
    {
      num: '1',
      title: 'Step 1 — Add Money (Wallet Top-Up)',
      icon: 'account_balance_wallet',
      color: 'bg-slate-100 border-slate-300 text-slate-900',
      badge: 'Razorpay Gateway',
      desc: 'Passengers and drivers can add funds to their Tap&Go digital wallet using Razorpay Standard Checkout (UPI, cards, netbanking).',
    },
    {
      num: '2',
      title: 'Step 2 — Wallet Balance Confirmation',
      icon: 'verified',
      color: 'bg-blue-50 border-blue-200 text-blue-700',
      badge: 'Balance Credit Confirmation',
      desc: 'Once Razorpay confirms the transaction signature, the corresponding wallet balance is updated automatically.',
    },
    {
      num: '3',
      title: 'Step 3 — Pay for a Ride (Internal Transfer)',
      icon: 'directions_car',
      color: 'bg-amber-50 border-amber-200 text-amber-700',
      badge: 'Passenger Wallet → Driver Wallet',
      desc: 'For normal ride transactions, the passenger pays using NFC card tap or QR code scan. The fare is transferred directly from the passenger wallet to the driver wallet inside the Tap&Go system.',
    },
    {
      num: '4',
      title: 'Step 4 — Driver Wallet Settlement',
      icon: 'savings',
      color: 'bg-emerald-50 border-emerald-200 text-emerald-700',
      badge: 'Transaction Record',
      desc: 'The driver receives immediate transaction confirmation, digital receipt, and updated wallet balance in their Tap&Go driver portal.',
    },
    {
      num: '5',
      title: 'Step 5 — Funds Withdrawal',
      icon: 'account_balance',
      color: 'bg-slate-100 border-slate-300 text-slate-900',
      badge: 'Email OTP Protected Withdrawal',
      desc: 'Drivers and passengers can submit withdrawal requests for accumulated wallet funds to their linked bank account or UPI ID with Email OTP verification.',
    },
  ]

  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8 sm:space-y-12">
        {/* Header */}
        <section className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 rounded-3xl p-6 sm:p-10 text-white shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-400/10 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 space-y-4 max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/20 border border-amber-400/40 text-amber-300 text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">account_tree</span>
              Payment Architecture
            </div>
            <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight">
              How Tap&amp;Go Payments Work
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              Understand the two-tier wallet architecture designed for seamless transport payments.
            </p>
          </div>
        </section>

        {/* Architecture Explanation Banner */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-slate-100 text-slate-900 flex items-center justify-center text-lg">
              💡
            </span>
            Wallet-Based Architecture Overview
          </h2>
          <p className="text-slate-700 leading-relaxed text-sm sm:text-base">
            Tap&amp;Go uses a specialized <strong>wallet-based payment architecture</strong> to ensure smooth ride payments without dependency on active payment gateway sessions during travel.
          </p>
          <div className="p-4 rounded-xl bg-slate-100 border border-slate-200 text-slate-900 text-xs sm:text-sm font-semibold leading-relaxed">
            <strong>Key Distinction:</strong> Razorpay is utilized exclusively for <strong>wallet funding (Add Money)</strong> and <strong>withdrawals</strong>. Individual passenger-to-driver ride payments are executed as internal wallet-to-wallet transfers within the Tap&amp;Go system.
          </div>
        </section>

        {/* Step-by-Step Flow */}
        <section className="space-y-6">
          <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center text-lg">
              🔄
            </span>
            End-to-End Payment Workflow
          </h2>

          <div className="space-y-4">
            {steps.map((step) => (
              <div key={step.num} className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex items-start gap-4">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border ${step.color}`}>
                    <span className="material-symbols-outlined text-2xl">{step.icon}</span>
                  </div>
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-extrabold text-slate-900 text-base sm:text-lg">{step.title}</h3>
                      <span className="px-2.5 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-slate-700 text-[11px] font-bold">
                        {step.badge}
                      </span>
                    </div>
                    <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">{step.desc}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Support Buttons Section */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-slate-900">headset_mic</span>
            <span className="font-bold text-slate-900 text-sm">Have Questions About Payments?</span>
          </div>
          <div className="flex flex-wrap gap-3">
            <a href="mailto:tapandgosupport@gmail.com" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 text-yellow-400 font-bold text-xs sm:text-sm hover:bg-slate-800 transition-colors">
              <span className="material-symbols-outlined text-base">mail</span>
              Email Support
            </a>
            <a href="tel:8779914564" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 text-white font-bold text-xs sm:text-sm hover:bg-emerald-700 transition-colors">
              <span className="material-symbols-outlined text-base">call</span>
              Call General Support
            </a>
            <a href="tel:9321768503" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500 text-slate-950 font-bold text-xs sm:text-sm hover:bg-amber-400 transition-colors">
              <span className="material-symbols-outlined text-base">credit_card_off</span>
              Call Lost Card Helpline
            </a>
          </div>
        </section>

        {/* Quick Links Banner */}
        <section className="bg-slate-900 rounded-3xl p-6 sm:p-8 text-white flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-xl font-bold text-amber-400">Ready to Experience Cashless Travel?</h3>
            <p className="text-xs sm:text-sm text-slate-300">Create an account or login to access your Tap&amp;Go digital wallet.</p>
          </div>
          <div className="flex gap-3">
            <Link to="/login" className="px-5 py-2.5 rounded-xl bg-amber-400 text-slate-950 font-bold text-xs sm:text-sm hover:bg-amber-300 transition-colors">
              Login to Wallet
            </Link>
            <Link to="/register" className="px-5 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white font-bold text-xs sm:text-sm hover:bg-slate-700 transition-colors">
              Register Account
            </Link>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default PaymentInfo
