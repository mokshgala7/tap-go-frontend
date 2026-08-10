import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'
import { Link } from '../routes/navigation.jsx'

export function RefundPolicy() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        {/* Header */}
        <section className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold uppercase tracking-wider">
            <span className="material-symbols-outlined text-sm">currency_exchange</span>
            Refund &amp; Cancellation Policy
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">
            Refund &amp; Cancellation Policy
          </h1>
          <p className="text-slate-500 text-xs sm:text-sm">
            Last Updated: August 2026
          </p>
        </section>

        {/* Content Body */}
        <div className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-8 text-slate-700 leading-relaxed text-sm sm:text-base">
          {/* Section 1: Ride Cancellations */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">1. Ride Cancellations</h2>
            <p>
              Tap&amp;Go processes fare payments at the point of interaction (NFC tap or QR scan) between passenger and driver upon ride completion. If a ride is cancelled before payment interaction occurs, no wallet deduction takes place.
            </p>
          </section>

          {/* Section 2: Wallet Transactions */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">2. Wallet Transactions</h2>
            <p>
              Completed wallet top-up transactions and internal passenger-to-driver wallet transfers are processed in real time and are not automatically reversible through the application. Users who encounter incorrect fare deductions or disputed transfers should contact support for manual review.
            </p>
          </section>

          {/* Section 3: Failed Transactions */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">3. Failed Wallet Top-Ups</h2>
            <p>
              If funds are debited from a user&apos;s bank account or UPI application during a wallet top-up but fail to reflect in the Tap&amp;Go wallet balance due to network issues or callback delays, the amount is typically auto-refunded by the issuing bank or payment gateway as per banking standards. If the balance remains uncredited, users can submit transaction proof to our support team.
            </p>
          </section>

          {/* Section 4: Duplicate Transactions */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">4. Duplicate Transactions</h2>
            <p>
              In the event of a technical glitch causing duplicate fare deductions for a single trip, users should report the transaction reference IDs to our support email. Once verified against backend logs, appropriate wallet adjustments will be initiated.
            </p>
          </section>

          {/* Section 5: Refund Request Process */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">5. How to Request Support or Refund Assistance</h2>
            <p>
              To lodge a dispute or request assistance regarding a wallet or ride transaction, please contact us with your account email, registered phone number, transaction ID, and transaction details:
            </p>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-800 space-y-2 font-medium text-sm">
              <p className="font-bold text-slate-900">Tap&amp;Go Refund Support</p>
              <p>Email: <a href="mailto:tapandgosupport@gmail.com" className="text-indigo-600 font-bold">tapandgosupport@gmail.com</a></p>
              <p>General Support Helpline: <span className="font-bold text-slate-900">8779914564</span></p>
              <p>Lost Card / Wallet Support: <span className="font-bold text-slate-900">9321768503</span></p>
              <p>Address: 7/711, Rajni Mahal, Opp. AC Market, Tardeo, Mumbai – 400034, Maharashtra, India</p>
            </div>
          </section>
        </div>
      </main>

      <Footer />
    </div>
  )
}

export default RefundPolicy
