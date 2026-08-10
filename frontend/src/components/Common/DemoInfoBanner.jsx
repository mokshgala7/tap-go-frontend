import React from 'react'

export function DemoInfoBanner() {
  return (
    <div className="w-full bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white border-b border-indigo-500/30 px-4 py-3 shadow-md">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs sm:text-sm font-medium">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center flex-shrink-0 text-indigo-300">
            <span className="material-symbols-outlined text-lg" aria-hidden="true">info</span>
          </div>
          <div>
            <span className="font-bold text-amber-400 tracking-wide uppercase text-[11px] block sm:inline sm:mr-2">
              Academic Demonstration Environment
            </span>
            <span className="text-slate-200">
              This deployment is provided for academic evaluation. Payment and wallet funding actions shown in Demo Mode are simulated and do not represent real financial transactions.
            </span>
          </div>
        </div>
        <a
          href="#/readme"
          className="inline-flex items-center gap-1 text-xs font-bold text-indigo-300 hover:text-amber-400 bg-indigo-900/50 hover:bg-indigo-900 px-3 py-1.5 rounded-lg border border-indigo-500/30 transition-colors whitespace-nowrap"
        >
          <span>Read Technical Notes</span>
          <span className="material-symbols-outlined text-sm" aria-hidden="true">arrow_forward</span>
        </a>
      </div>
    </div>
  )
}

export default DemoInfoBanner
