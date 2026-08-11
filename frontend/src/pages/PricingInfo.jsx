import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'
import { Link } from '../routes/navigation.jsx'

export function PricingInfo() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        {/* Header */}
        <section className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-6 sm:p-10 text-white shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-400/10 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 space-y-4 max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/20 border border-amber-400/40 text-amber-300 text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">payments</span>
              Pricing &amp; Fares
            </div>
            <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight">
              Pricing &amp; Fare Information
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              Transparent information regarding ride fare processing, digital wallet transactions, and NFC card delivery on Tap&amp;Go.
            </p>
          </div>
        </section>

        {/* Fare Principles */}
        <div className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-8 text-slate-700 leading-relaxed text-sm sm:text-base">
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">1. Ride Fare Structure</h2>
            <p>
              Tap&amp;Go is a cashless digital payment facilitator for taxis and auto-rickshaws.
            </p>
            <ul className="list-disc list-inside space-y-2 pl-2 text-slate-600">
              <li>Ride fares are calculated based on the applicable transportation arrangement or driver meter calculation for the trip.</li>
              <li>Tap&amp;Go records and processes the exact fare amount agreed upon or entered during the payment interaction.</li>
              <li>The full ride fare is transferred directly from the passenger&apos;s digital wallet to the driver&apos;s digital wallet.</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">2. Wallet Top-Up &amp; Fee Transparency</h2>
            <p>
              Tap&amp;Go displays wallet top-up details prior to confirmation.
            </p>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 text-xs sm:text-sm space-y-1 font-medium">
              <p className="font-bold text-slate-900">Fee Disclosure:</p>
              <p>
                Any applicable platform, payment processing, or withdrawal charges will be disclosed to the user before confirmation where applicable.
              </p>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">3. Driver Wallet Settlement</h2>
            <p>
              Fares earned by drivers accumulate instantly in their Tap&amp;Go driver wallet. Drivers can review transaction receipts, track daily earnings, and request wallet balance withdrawals through supported withdrawal mechanisms.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">4. NFC Card &amp; Location-Based Delivery Charges</h2>
            <p>
              The customer-facing price of a physical Tap&amp;Go NFC card is <strong>₹50</strong>. An applicable location-based shipping fee is calculated separately based on the destination address (Local Mumbai / Maharashtra Regional / National). The exact price breakdown (Card ₹50 + Shipping ₹X = Total ₹Y) is clearly displayed before order confirmation.
            </p>
          </section>

          {/* Quick Actions */}
          <section className="pt-4 flex flex-wrap gap-4">
            <Link to="/shipping-policy" className="px-5 py-2.5 rounded-xl bg-indigo-600 text-white font-bold text-xs sm:text-sm hover:bg-indigo-700 transition-colors">
              Shipping &amp; Delivery Policy
            </Link>
            <Link to="/contact" className="px-5 py-2.5 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 font-bold text-xs sm:text-sm hover:bg-slate-200 transition-colors">
              Contact Support
            </Link>
          </section>
        </div>
      </main>

      <Footer />
    </div>
  )
}

export default PricingInfo
