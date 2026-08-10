import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'

export function ShippingPolicy() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        {/* Header */}
        <section className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold uppercase tracking-wider">
            <span className="material-symbols-outlined text-sm">local_shipping</span>
            Shipping &amp; Delivery Policy
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">
            Shipping &amp; Delivery Policy
          </h1>
          <p className="text-slate-500 text-xs sm:text-sm">
            Last Updated: August 2026
          </p>
        </section>

        {/* Content Body */}
        <div className="bg-white rounded-2xl p-6 sm:p-10 shadow-sm border border-slate-200 space-y-8 text-slate-700 leading-relaxed text-sm sm:text-base">
          {/* Statement */}
          <div className="p-5 rounded-2xl bg-blue-50/80 border border-blue-200 text-blue-950 font-medium space-y-2">
            <h2 className="text-lg font-bold text-blue-900">Digital Service Platform Disclosure</h2>
            <p className="text-sm leading-relaxed">
              <strong>Tap&amp;Go is a digital transportation payment platform and does not operate an e-commerce shipping or physical-goods delivery service through this website.</strong>
            </p>
          </div>

          {/* Policy Details */}
          <section className="space-y-4">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">Policy Details</h2>
            <ul className="list-disc list-inside space-y-3 pl-2 text-slate-600">
              <li>
                <strong>Digital Services Only:</strong> The Tap&amp;Go platform primarily provides digital wallet funding, cashless ride payment processing, transaction management, and driver wallet withdrawal services.
              </li>
              <li>
                <strong>No Physical Goods Sold:</strong> No physical e-commerce merchandise or retail items are sold or delivered via this website.
              </li>
              <li>
                <strong>No Standard Shipping Required:</strong> Since transactions represent digital wallet top-ups and fare settlements, standard postal shipping or delivery tracking protocols do not apply to website transactions.
              </li>
              <li>
                <strong>Prototype Hardware Clarification:</strong> Tap&amp;Go may demonstrate prototype hardware such as an NFC card and ESP32-S3 POS terminal as part of the academic project. These prototypes are not sold as e-commerce products through this website.
              </li>
            </ul>
          </section>

          {/* Contact Section */}
          <section className="space-y-3">
            <h2 className="text-xl font-bold text-slate-900 border-b border-slate-100 pb-2">Contact &amp; Inquiries</h2>
            <p>For questions regarding hardware deployment or digital services, please reach out to our team:</p>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-800 space-y-1 font-medium text-sm">
              <p className="font-bold text-slate-900">Tap&amp;Go Support</p>
              <p>Email: <a href="mailto:tapandgosupport@gmail.com" className="text-indigo-600 font-bold">tapandgosupport@gmail.com</a></p>
              <p>General Support: 8779914564</p>
              <p>Address: 7/711, Rajni Mahal, Opp. AC Market, Tardeo, Mumbai – 400034, Maharashtra, India</p>
            </div>
          </section>
        </div>
      </main>

      <Footer />
    </div>
  )
}

export default ShippingPolicy
