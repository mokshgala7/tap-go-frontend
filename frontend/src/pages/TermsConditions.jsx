import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'

export function TermsConditions() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        {/* Header */}
        <section className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-bold uppercase tracking-wider">
            <span className="material-symbols-outlined text-sm">gavel</span>
            Terms &amp; Conditions
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">
            Terms of Service &amp; User Agreement
          </h1>
          <p className="text-slate-500 text-xs sm:text-sm">
            Last Updated: August 2026
          </p>
        </section>

        {/* Terms Body */}
        <div className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-8 text-slate-700 leading-relaxed text-sm sm:text-base">
          {/* Section 1 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">1. Scope &amp; Nature of Service</h2>
            <p>
              Welcome to Tap&amp;Go. Tap&amp;Go is a smart cashless payment technology platform designed for taxi and auto-rickshaw transport payments.
            </p>
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-950 text-xs sm:text-sm font-semibold space-y-1">
              <p className="font-bold text-amber-900">Academic Project Notice:</p>
              <p>
                Tap&amp;Go is a student / final-year project developed by Moksh Gala, a Diploma student in Computer Science &amp; Engineering at SVKM’s Shri Bhagubai Mafatlal Polytechnic. It is designed for demonstration and technological evaluation purposes and is not a licensed financial institution or RBI-regulated payment aggregator.
              </p>
            </div>
          </section>

          {/* Section 2 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">2. Account Registration</h2>
            <p>
              Users may register for either a <strong>Passenger Account</strong> or a <strong>Driver Account</strong>. By registering, users agree to provide accurate, current, and complete personal information. Users are responsible for safeguarding login credentials and session integrity.
            </p>
          </section>

          {/* Section 3 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">3. Wallet Architecture &amp; Usage</h2>
            <ul className="list-disc list-inside space-y-2 pl-2 text-slate-600">
              <li><strong>Adding Money:</strong> Users may add balance to their Tap&amp;Go digital wallet using supported external payment gateway channels.</li>
              <li><strong>Ride Payments:</strong> Standard ride payments between passengers and drivers are executed as internal wallet-to-wallet transfers. The external payment gateway is not invoked for individual ride payments.</li>
              <li><strong>Driver Withdrawals:</strong> Drivers with verified balances can request wallet funds withdrawal through supported withdrawal mechanisms.</li>
            </ul>
          </section>

          {/* Section 4 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">4. User Responsibilities &amp; Security</h2>
            <p>
              Users agree not to engage in fraudulent wallet top-ups, unauthorized card usage, transaction manipulation, or suspicious account activities. Tap&amp;Go incorporates automated AI fraud monitoring and OTP verification protocols to safeguard transactions.
            </p>
          </section>

          {/* Section 5 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">5. Lost Cards &amp; Compromised Accounts</h2>
            <p>
              If a physical Tap&amp;Go card is lost or an account is compromised, the user must immediately contact support at <strong>9321768503</strong> or email <strong>tapandgosupport@gmail.com</strong> to request account suspension or card blocking.
            </p>
          </section>

          {/* Section 6 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">6. Disclaimers &amp; Limitation of Liability</h2>
            <p>
              The platform and its services are provided on an &quot;as is&quot; and &quot;as available&quot; basis for evaluation purposes. Tap&amp;Go shall not be liable for indirect, incidental, or consequential damages resulting from platform downtime, network errors, or external hosting service restarts.
            </p>
          </section>

          {/* Section 7 */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">7. Support &amp; Contact</h2>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-800 space-y-1 font-medium text-sm">
              <p className="font-bold text-slate-900">Tap&amp;Go Support Team</p>
              <p>Email: <a href="mailto:tapandgosupport@gmail.com" className="text-indigo-600 font-bold">tapandgosupport@gmail.com</a></p>
              <p>General Support: 8779914564 | Lost Card Support: 9321768503</p>
              <p>Address: 7/711, Rajni Mahal, Opp. AC Market, Tardeo, Mumbai – 400034, Maharashtra, India</p>
            </div>
          </section>
        </div>
      </main>

      <Footer />
    </div>
  )
}

export default TermsConditions
