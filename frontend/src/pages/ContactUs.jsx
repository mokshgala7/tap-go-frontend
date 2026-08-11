import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'
import { Link } from '../routes/navigation.jsx'

export function ContactUs() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8 sm:space-y-12">
        {/* Header */}
        <section className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-6 sm:p-10 text-white shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-400/10 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 space-y-4 max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/20 border border-amber-400/40 text-amber-300 text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">support_agent</span>
              Get in Touch
            </div>
            <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight">
              Contact Tap&amp;Go Support
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              We are here to assist you with any questions regarding wallet operations, NFC card orders &amp; delivery, lost card assistance, ride payments, or technical inquiries.
            </p>
          </div>
        </section>

        {/* Contact Cards Grid */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-2xl">mail</span>
            </div>
            <h2 className="text-lg font-bold text-slate-900">Email Support</h2>
            <p className="text-xs text-slate-600">Send your queries, NFC card delivery requests, or dispute reports to our support team.</p>
            <div>
              <a href="mailto:tapandgosupport@gmail.com" className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white font-bold text-xs hover:bg-indigo-700 transition-colors">
                <span className="material-symbols-outlined text-sm">mail</span>
                tapandgosupport@gmail.com
              </a>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-100 text-emerald-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-2xl">call</span>
            </div>
            <h2 className="text-lg font-bold text-slate-900">General &amp; Card Delivery Support</h2>
            <p className="text-xs text-slate-600">For general platform inquiries, card shipping status, and user support assistance.</p>
            <div>
              <a href="tel:8779914564" className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 text-white font-bold text-sm hover:bg-emerald-700 transition-colors">
                <span className="material-symbols-outlined text-sm">call</span>
                8779914564
              </a>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-amber-50 border border-amber-100 text-amber-600 flex items-center justify-center">
              <span className="material-symbols-outlined text-2xl">credit_card_off</span>
            </div>
            <h2 className="text-lg font-bold text-slate-900">Lost Card / Wallet Support</h2>
            <p className="text-xs text-slate-600">Helpline for lost NFC cards or compromised wallet accounts.</p>
            <div>
              <a href="tel:9321768503" className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 text-slate-950 font-bold text-sm hover:bg-amber-400 transition-colors">
                <span className="material-symbols-outlined text-sm">phone_in_talk</span>
                9321768503
              </a>
            </div>
          </div>
        </section>

        {/* Physical Address Section */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-800 flex items-center justify-center font-bold text-lg">
              📍
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">Project Support Address</h2>
          </div>
          <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 text-slate-800 space-y-1 font-medium text-sm sm:text-base leading-relaxed">
            <p className="font-bold text-slate-900">Tap&amp;Go Project Support</p>
            <p>7/711, Rajni Mahal,</p>
            <p>Opp. AC Market, Tardeo,</p>
            <p>Mumbai – 400034,</p>
            <p>Maharashtra, India</p>
          </div>
        </section>

        {/* Quick Links Banner */}
        <section className="bg-slate-900 rounded-3xl p-6 sm:p-8 text-white flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-xl font-bold text-amber-400">Need Immediate Help with a Lost Card?</h3>
            <p className="text-xs sm:text-sm text-slate-300">Visit our dedicated lost card &amp; account protection support portal.</p>
          </div>
          <Link to="/lost-card" className="px-5 py-2.5 rounded-xl bg-amber-400 text-slate-950 font-bold text-xs sm:text-sm hover:bg-amber-300 transition-colors">
            Lost Card Assistance
          </Link>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default ContactUs
