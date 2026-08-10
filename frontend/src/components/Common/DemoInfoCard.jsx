import React from 'react'

export function DemoInfoCard({ type = 'database', className = '' }) {
  if (type === 'database') {
    return (
      <div className={`rounded-2xl border border-blue-200 bg-blue-50/70 p-5 text-slate-800 shadow-sm ${className}`}>
        <div className="flex items-start gap-3.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
            <span className="material-symbols-outlined text-xl" aria-hidden="true">database</span>
          </div>
          <div className="space-y-2 text-xs sm:text-sm leading-relaxed">
            <div className="flex items-center gap-2">
              <span className="font-bold text-blue-900 text-sm">Demonstration Deployment &amp; Database Persistence</span>
              <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-700">
                Notice
              </span>
            </div>
            <p className="text-slate-700">
              This deployment uses <strong>Render Free Tier hosting</strong>. The backend database is <strong>REAL and fully functional</strong> while the server is live. All registrations, profile edits, wallet transactions, and other operations are saved normally in the active database.
            </p>
            <p className="text-slate-700">
              However, Render Free Tier stores its active database inside temporary server storage. Whenever the Render server rebuilds or restarts, a <strong>clean seeded database snapshot is automatically restored</strong>. This behaviour is intentional so every reviewer always starts with a clean demonstration environment. Newly created accounts should be treated as temporary demonstration accounts.
            </p>
            <div className="mt-3 rounded-xl border border-blue-200 bg-white/80 p-3">
              <span className="font-bold text-blue-900 text-xs block mb-1">Production Version:</span>
              <ul className="list-disc list-inside text-xs text-slate-600 space-y-0.5 font-medium">
                <li>Database will use persistent managed storage (e.g. AWS RDS MySQL).</li>
                <li>All registrations will remain permanently.</li>
                <li>User accounts will never reset after deployment or restart.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (type === 'otp') {
    return (
      <div className={`rounded-2xl border border-amber-200 bg-amber-50/75 p-4 sm:p-5 text-slate-800 shadow-sm ${className}`}>
        <div className="flex items-start gap-3.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-white shadow-sm">
            <span className="material-symbols-outlined text-xl" aria-hidden="true">mail</span>
          </div>
          <div className="space-y-2 text-xs sm:text-sm leading-relaxed">
            <div className="flex items-center gap-2">
              <span className="font-bold text-amber-950 text-sm">Email OTP Verification Notice</span>
              <span className="rounded-full bg-amber-200/60 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-900">
                Email OTP
              </span>
            </div>
            <p className="text-slate-700">
              <strong>Current Deployment:</strong> Verification OTPs are sent to your <strong>registered email address</strong>. In this demonstration environment, to ensure reviewers are never blocked by external email delays or rate limits, a secure six-digit OTP is automatically generated and displayed/filled so you can complete verification seamlessly.
            </p>
            <div className="mt-2.5 rounded-xl border border-amber-200 bg-white/80 p-3">
              <span className="font-bold text-amber-950 text-xs block mb-1">Production Behaviour:</span>
              <ul className="list-disc list-inside text-xs text-slate-600 space-y-0.5 font-medium">
                <li>Backend generates a secure 6-digit OTP.</li>
                <li>OTP is sent to the user's registered email address via the backend email service (Gmail SMTP / Production Mailer).</li>
                <li>User enters the received email OTP.</li>
                <li>Backend validates the OTP before authentication or verification.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (type === 'documents') {
    return (
      <div className={`rounded-2xl border border-indigo-200 bg-indigo-50/70 p-4 sm:p-5 text-slate-800 shadow-sm ${className}`}>
        <div className="flex items-start gap-3.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <span className="material-symbols-outlined text-xl" aria-hidden="true">folder_open</span>
          </div>
          <div className="space-y-2 text-xs sm:text-sm leading-relaxed">
            <div className="flex items-center gap-2">
              <span className="font-bold text-indigo-950 text-sm">Uploaded Document Storage &amp; Previews</span>
              <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-indigo-700">
                Storage Note
              </span>
            </div>
            <p className="text-slate-700">
              Uploaded document previews are unavailable or temporary in this demonstration deployment because Render Free Tier uses temporary server storage. Uploaded files cannot be retained permanently after server rebuilds or redeployments.
            </p>
            <div className="mt-2 rounded-xl border border-indigo-200 bg-white/80 p-2.5">
              <span className="font-bold text-indigo-950 text-xs block mb-0.5">Production Deployment:</span>
              <p className="text-xs text-slate-600 font-medium">
                Production deployment will store uploaded documents securely using persistent object storage (e.g. AWS S3 / Google Cloud Storage), allowing administrators and users to access and preview uploaded files normally.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (type === 'admin_dashboard') {
    return (
      <div className={`rounded-2xl border border-slate-700 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 p-5 text-white shadow-xl ${className}`}>
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-400 text-slate-950 shadow-md">
            <span className="material-symbols-outlined text-2xl" aria-hidden="true">verified</span>
          </div>
          <div className="space-y-2.5 text-xs sm:text-sm leading-relaxed flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-700/60 pb-2.5">
              <div>
                <span className="font-black text-amber-400 text-base block tracking-tight">Demo Environment Information</span>
                <span className="text-slate-400 text-xs font-medium">Prepared for Technical Review &amp; Demonstration</span>
              </div>
              <span className="rounded-full bg-amber-400/20 border border-amber-400/30 px-3 py-1 text-xs font-bold text-amber-300">
                Reviewer Access Active
              </span>
            </div>
            <p className="text-slate-300">
              This demonstration deployment showcases the Tap&amp;Go platform. The application's complete business workflow is fully operational.
            </p>
            <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-3">
              <span className="font-bold text-slate-200 text-xs block mb-1">Simulated Production Services (Render Free Tier Hosting):</span>
              <ul className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-slate-300 font-medium">
                <li className="flex items-center gap-1.5 bg-slate-900/60 px-2.5 py-1.5 rounded-lg border border-slate-700">
                  <span className="text-amber-400 font-bold">•</span> Temporary Database Storage
                </li>
                <li className="flex items-center gap-1.5 bg-slate-900/60 px-2.5 py-1.5 rounded-lg border border-slate-700">
                  <span className="text-amber-400 font-bold">•</span> Email OTP Verification
                </li>
                <li className="flex items-center gap-1.5 bg-slate-900/60 px-2.5 py-1.5 rounded-lg border border-slate-700">
                  <span className="text-amber-400 font-bold">•</span> Temporary Upload Document Storage
                </li>
              </ul>
            </div>
            <p className="text-amber-300/90 text-xs font-semibold">
              The payment workflow, authentication flow, and business logic remain identical to the intended production implementation.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return null
}

export default DemoInfoCard
