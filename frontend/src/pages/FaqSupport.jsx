import React, { useState } from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'

export function FaqSupport() {
  const [openIdx, setOpenIdx] = useState(null)

  const faqs = [
    {
      q: 'What is Tap&Go?',
      a: 'Tap&Go is a smart cashless payment platform designed for taxis and auto-rickshaws. It enables passengers to pay fares using NFC card taps or QR code scans, while providing drivers with digital wallet balances and real-time transaction records.',
    },
    {
      q: 'Who can use Tap&Go?',
      a: 'Tap&Go is designed for both passengers and drivers in public transportation. Passengers use it for cashless fare payments, while drivers use it to receive payments, track earnings, and manage wallet withdrawals.',
    },
    {
      q: 'How do I add money to my wallet?',
      a: 'You can add funds to your Tap&Go digital wallet by clicking "Recharge" or "Add Money" inside your passenger or driver dashboard. Top-ups are processed using supported payment gateways via UPI, debit/credit card, or netbanking.',
    },
    {
      q: 'How do I pay for a ride?',
      a: 'When your ride is complete, tap your Tap&Go NFC card on the driver’s smart POS terminal or scan the driver’s dynamic QR code using your smartphone. The fare is transferred from your passenger wallet to the driver’s wallet.',
    },
    {
      q: 'Do I need physical cash for travel?',
      a: 'No. Tap&Go is built to reduce reliance on physical cash and exact-change friction during taxi and auto-rickshaw rides.',
    },
    {
      q: 'What happens if a wallet funding transaction fails?',
      a: 'If a payment is debited from your bank account but the Tap&Go wallet is not credited, the transaction will be checked against the payment status/callback information and the applicable payment provider’s refund process. You can contact support at tapandgosupport@gmail.com with transaction details.',
    },
    {
      q: 'What happens if I see a suspicious transaction?',
      a: 'Tap&Go incorporates AI-assisted fraud detection monitoring. If a transaction appears unusual, an email OTP verification is triggered. You can also report disputed transactions immediately to our support team.',
    },
    {
      q: 'What should I do if I lose my Tap&Go card?',
      a: 'If you lose your physical Tap&Go card, immediately call our dedicated lost card support helpline at 9321768503 to report the card and protect your account.',
    },
    {
      q: 'How do I contact Tap&Go support?',
      a: 'You can reach us via email at tapandgosupport@gmail.com, call general support at 8779914564, call lost card helpline at 9321768503, or reach Tap&Go Project Support at 7/711, Rajni Mahal, Opp. AC Market, Tardeo, Mumbai – 400034, Maharashtra, India.',
    },
  ]

  const toggle = (idx) => {
    setOpenIdx(openIdx === idx ? null : idx)
  }

  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        {/* Header */}
        <section className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-6 sm:p-10 text-white shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-400/10 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 space-y-4 max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/20 border border-amber-400/40 text-amber-300 text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">help</span>
              Help &amp; Support
            </div>
            <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight">
              Frequently Asked Questions
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              Find answers to common questions about Tap&amp;Go wallets, payments, NFC travel, and lost card assistance.
            </p>
          </div>
        </section>

        {/* FAQ Accordion List */}
        <section className="space-y-4">
          {faqs.map((faq, idx) => {
            const isOpen = openIdx === idx
            return (
              <div key={idx} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm transition-all duration-200">
                <button
                  type="button"
                  onClick={() => toggle(idx)}
                  className="w-full text-left p-5 sm:p-6 flex items-center justify-between gap-4 focus:outline-none"
                >
                  <span className="font-bold text-slate-900 text-base sm:text-lg">{faq.q}</span>
                  <span className="material-symbols-outlined text-indigo-600 shrink-0">
                    {isOpen ? 'expand_less' : 'expand_more'}
                  </span>
                </button>
                {isOpen && (
                  <div className="px-5 pb-6 sm:px-6 text-xs sm:text-sm text-slate-600 leading-relaxed border-t border-slate-100 pt-4">
                    {faq.a}
                  </div>
                )}
              </div>
            )
          })}
        </section>

        {/* Support Contact Box */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <h2 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center text-lg">
              📞
            </span>
            Still Need Help?
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs sm:text-sm text-slate-700">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="font-bold block text-slate-900">Email Support</span>
              <a href="mailto:tapandgosupport@gmail.com" className="inline-flex items-center gap-1.5 text-indigo-600 font-bold break-all hover:underline">
                <span className="material-symbols-outlined text-sm">mail</span>
                tapandgosupport@gmail.com
              </a>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="font-bold block text-slate-900">General Support</span>
              <a href="tel:8779914564" className="inline-flex items-center gap-1.5 text-emerald-600 font-bold hover:underline">
                <span className="material-symbols-outlined text-sm">call</span>
                8779914564
              </a>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="font-bold block text-slate-900">Lost Card Support</span>
              <a href="tel:9321768503" className="inline-flex items-center gap-1.5 text-amber-600 font-bold hover:underline">
                <span className="material-symbols-outlined text-sm">phone_in_talk</span>
                9321768503
              </a>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default FaqSupport
