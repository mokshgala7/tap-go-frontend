import React from 'react'

export function DevBanner() {
  return (
    <div
      className="w-full bg-slate-900 border-b border-amber-500/30 text-slate-100 px-4 py-2.5 shadow-md flex items-center justify-center text-xs sm:text-sm font-medium transition-all"
      role="region"
      aria-label="Development Notification Banner"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-center gap-2 text-center">
        <span className="text-base shrink-0" role="img" aria-label="under-construction">
          🚧
        </span>
        <span>
          <strong className="text-amber-400 font-bold">Tap &amp; Go</strong> is currently under development. Some features may be unavailable while we complete development and testing.
        </span>
      </div>
    </div>
  )
}

export default DevBanner
