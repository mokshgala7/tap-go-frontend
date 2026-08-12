import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'
import { Link } from '../routes/navigation.jsx'

export function LostCardSupport() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        {/* Header */}
        <section className="bg-gradient-to-br from-rose-950 via-slate-900 to-slate-900 rounded-3xl p-6 sm:p-10 text-white shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-400/10 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 space-y-4 max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/20 border border-rose-400/40 text-rose-300 text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">warning</span>
              Emergency Helpline
            </div>
            <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight">
              Lost Card &amp; Account Assistance
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              If you have lost your physical Tap&amp;Go NFC card or suspect unauthorized wallet activity, take immediate action by contacting support.
            </p>
          </div>
        </section>

        {/* Emergency Call Box */}
        <section className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-rose-200 space-y-6 text-center">
          <div className="w-16 h-16 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center mx-auto text-3xl">
            <span className="material-symbols-outlined text-3xl">phone_in_talk</span>
          </div>

          <div className="space-y-2">
            <h2 className="text-xs uppercase font-extrabold tracking-widest text-slate-500">Dedicated Lost Card Support Helpline</h2>
            <a href="tel:9321768503" className="inline-block text-4xl sm:text-5xl font-black text-rose-600 hover:text-rose-700 tracking-tight">
              9321768503
            </a>
            <p className="text-xs sm:text-sm text-slate-600 font-medium pt-1">
              Call immediately for account assistance and lost card support.
            </p>
          </div>

          <div className="flex justify-center gap-3 pt-2">
            <a href="tel:9321768503" className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-rose-600 text-white font-bold text-sm hover:bg-rose-700 transition-colors shadow-sm">
              <span className="material-symbols-outlined">call</span>
              Call Lost Card Support Now
            </a>
            <a href="mailto:tapandgosupport@gmail.com" className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-slate-800 text-white font-bold text-sm hover:bg-slate-700 transition-colors shadow-sm">
              <span className="material-symbols-outlined">mail</span>
              Email Support
            </a>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 text-xs sm:text-sm max-w-2xl mx-auto space-y-1">
            <p className="font-bold text-slate-900">Email Support Backup:</p>
            <p>
              Send an urgent report to <a href="mailto:tapandgosupport@gmail.com" className="text-slate-900 font-bold hover:underline">tapandgosupport@gmail.com</a> with your registered phone number and account email.
            </p>
          </div>
        </section>

        {/* Recommended Action Steps */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center text-lg">
              🛡️
            </span>
            Steps to Take Immediately
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="font-extrabold text-rose-600 text-base block">1. Call Support</span>
              <p className="text-xs text-slate-600 leading-relaxed">
                Dial <strong>9321768503</strong> to report a lost card and request account assistance.
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="font-extrabold text-slate-900 text-base block">2. Lock Account Session</span>
              <p className="text-xs text-slate-600 leading-relaxed">
                Log into your Tap&amp;Go portal and update your password or lock your active browser session.
              </p>
            </div>

            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="font-extrabold text-emerald-600 text-base block">3. Support Replacement</span>
              <p className="text-xs text-slate-600 leading-relaxed">
                Request replacement card linkage assistance from the Tap&amp;Go support team.
              </p>
            </div>
          </div>
        </section>

        {/* Quick Return Action */}
        <section className="bg-slate-900 rounded-3xl p-6 sm:p-8 text-white flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-xl font-bold text-amber-400">Account Access</h3>
            <p className="text-xs sm:text-sm text-slate-300">Access your dashboard to view active wallet sessions and transaction history.</p>
          </div>
          <Link to="/login" className="px-5 py-2.5 rounded-xl bg-amber-400 text-slate-950 font-bold text-xs sm:text-sm hover:bg-amber-300 transition-colors">
            Go to Login
          </Link>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default LostCardSupport
