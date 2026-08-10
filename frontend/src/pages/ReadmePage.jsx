import React from 'react'
import Navbar from '../components/Common/Navbar.jsx'
import Footer from '../components/Common/Footer.jsx'
import DemoInfoCard from '../components/Common/DemoInfoCard.jsx'
import { Link } from '../routes/navigation.jsx'

export function ReadmePage() {
  return (
    <div className="bg-slate-50 min-h-screen text-slate-900 flex flex-col font-sans selection:bg-amber-200 selection:text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8 sm:space-y-12">
        {/* Header */}
        <section className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-6 sm:p-10 text-white shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-400/10 rounded-full blur-3xl pointer-events-none"></div>
          <div className="relative z-10 space-y-4 max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/20 border border-amber-400/40 text-amber-300 text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">verified</span>
              Tap&amp;Go Technical &amp; System Architecture
            </div>
            <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight">
              System Architecture &amp; Deployment Guide
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              This verification guide details the architecture, demonstration workflow, temporary hosting limitations, and intended production setup for the Tap&amp;Go platform.
            </p>
          </div>
        </section>

        {/* 1. Purpose */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center font-bold text-lg">
              1
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">Project Purpose</h2>
          </div>
          <p className="text-slate-700 leading-relaxed text-sm sm:text-base">
            This live demonstration deployment showcases the end-to-end user workflows of <strong>Tap&amp;Go</strong>, including passenger and driver registration, login, wallet management, trip payment simulation, and administrative controls.
          </p>
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-950 text-xs sm:text-sm font-semibold flex items-start gap-3">
            <span className="material-symbols-outlined text-amber-600 text-xl shrink-0">info</span>
            <span>
              All features operate in a complete business workflow. Infrastructure limitations of the free hosting environment have been intentional simulated and are documented below.
            </span>
          </div>
        </section>

        {/* 2. System Architecture */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-800 flex items-center justify-center font-bold text-lg">
              2
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">System Architecture</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">Frontend</span>
              <h3 className="font-extrabold text-slate-900 text-lg">Vercel</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                React single-page application built with Vite and Tailwind CSS, deployed on Vercel high-speed global CDN.
              </p>
            </div>
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">Backend API</span>
              <h3 className="font-extrabold text-slate-900 text-lg">Render</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                FastAPI Python REST API backend hosting authentication, wallet operations, verification, and payment services.
              </p>
            </div>
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider block">Demonstration DB</span>
              <h3 className="font-extrabold text-slate-900 text-lg">Render Ephemeral Storage</h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                SQLAlchemy engine backed by SQLite snapshot, running directly within the active Render web container.
              </p>
            </div>
          </div>
        </section>

        {/* 3. Database Behaviour & Registration */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 text-blue-800 flex items-center justify-center font-bold text-lg">
              3
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">Database Behaviour &amp; Account Registration</h2>
          </div>
          <p className="text-slate-700 leading-relaxed text-sm sm:text-base">
            The backend database is <strong>fully real and operational while the server is live</strong>. Account registrations, wallet updates, balances, transactions, and admin approvals update database records immediately.
          </p>
          <DemoInfoCard type="database" />
        </section>

        {/* 4. OTP & Documents */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center font-bold text-lg">
                  4
                </div>
                <h2 className="text-xl font-black text-slate-900 tracking-tight">OTP Verification</h2>
              </div>
              <p className="text-slate-700 text-xs sm:text-sm leading-relaxed mb-4">
                How one-time password verification works in this demonstration vs live production.
              </p>
            </div>
            <DemoInfoCard type="otp" />
          </div>

          <div className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-800 flex items-center justify-center font-bold text-lg">
                  5
                </div>
                <h2 className="text-xl font-black text-slate-900 tracking-tight">Uploaded Documents</h2>
              </div>
              <p className="text-slate-700 text-xs sm:text-sm leading-relaxed mb-4">
                Handling of driver licences, vehicle RC, Aadhaar and PAN documents.
              </p>
            </div>
            <DemoInfoCard type="documents" />
          </div>
        </section>

        {/* 5. Payment Gateway */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold text-lg">
              6
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">Payment Gateway Integration</h2>
          </div>
          <p className="text-slate-700 leading-relaxed text-sm sm:text-base">
            Current deployment demonstrates the complete payment workflow using a dynamic UPI QR integration.
          </p>
          <div className="p-5 rounded-2xl bg-emerald-50/70 border border-emerald-200 space-y-3">
            <div className="flex items-center gap-2 text-emerald-950 font-bold text-sm">
              <span className="material-symbols-outlined text-emerald-600">published_with_changes</span>
              <span>Post-Approval Migration Plan</span>
            </div>
            <p className="text-slate-700 text-xs sm:text-sm leading-relaxed">
              When linked with a production <strong>Payment Gateway</strong>, the demonstration payment implementation is replaced with live Payment Gateway SDKs &amp; Webhook Callbacks. The overall user wallet experience, transaction recording, and interface will remain completely unchanged.
            </p>
          </div>
        </section>

        {/* 6. Production Comparison Table */}
        <section className="bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-800 flex items-center justify-center font-bold text-lg">
              7
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">Production vs Demo Comparison</h2>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-slate-200">
            <table className="w-full text-left text-xs sm:text-sm">
              <thead className="bg-slate-900 text-white uppercase text-[11px] tracking-wider font-bold">
                <tr>
                  <th className="p-4 sm:p-5">Feature</th>
                  <th className="p-4 sm:p-5">Demo Deployment (Hosted)</th>
                  <th className="p-4 sm:p-5">Production Environment</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-medium text-slate-700">
                <tr className="hover:bg-slate-50">
                  <td className="p-4 sm:p-5 font-bold text-slate-900">Database Storage</td>
                  <td className="p-4 sm:p-5 text-amber-700 bg-amber-50/40">Temporary Render Container Storage (Reset on restart)</td>
                  <td className="p-4 sm:p-5 text-emerald-700 font-bold bg-emerald-50/40">Persistent Managed Database (AWS RDS / Managed MySQL)</td>
                </tr>
                <tr className="hover:bg-slate-50">
                  <td className="p-4 sm:p-5 font-bold text-slate-900">OTP Delivery</td>
                  <td className="p-4 sm:p-5 text-amber-700 bg-amber-50/40">Auto-Filled Email OTP (Demo Mode)</td>
                  <td className="p-4 sm:p-5 text-emerald-700 font-bold bg-emerald-50/40">Real Email OTP Delivery (Registered Email Address)</td>
                </tr>
                <tr className="hover:bg-slate-50">
                  <td className="p-4 sm:p-5 font-bold text-slate-900">Uploaded Documents</td>
                  <td className="p-4 sm:p-5 text-amber-700 bg-amber-50/40">Temporary Server File Storage</td>
                  <td className="p-4 sm:p-5 text-emerald-700 font-bold bg-emerald-50/40">Permanent Secure Object Storage (AWS S3 / Google Cloud)</td>
                </tr>
                <tr className="hover:bg-slate-50">
                  <td className="p-4 sm:p-5 font-bold text-slate-900">Payment Gateway</td>
                  <td className="p-4 sm:p-5 text-amber-700 bg-amber-50/40">Demonstration UPI Integration</td>
                  <td className="p-4 sm:p-5 text-emerald-700 font-bold bg-emerald-50/40">Production Payment Gateway SDK &amp; Webhooks</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* Quick Links */}
        <section className="bg-slate-900 rounded-3xl p-6 sm:p-8 text-white flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-xl font-bold text-amber-400">Ready to test the application?</h3>
            <p className="text-xs sm:text-sm text-slate-300">Try logging in with pre-filled demo accounts or create a new temporary test user.</p>
          </div>
          <div className="flex gap-3">
            <Link to="/login" className="px-5 py-2.5 rounded-xl bg-amber-400 text-slate-950 font-bold text-xs sm:text-sm hover:bg-amber-300 transition-colors">
              Go to Login
            </Link>
            <Link to="/register" className="px-5 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white font-bold text-xs sm:text-sm hover:bg-slate-700 transition-colors">
              Try Register
            </Link>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default ReadmePage
