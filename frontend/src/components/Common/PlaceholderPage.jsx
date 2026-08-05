import { Link } from '../../routes/navigation.jsx'

function PlaceholderPage({ title, description }) {
  return (
    <main className="min-h-screen bg-surface px-6 py-20 text-on-surface">
      <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-6 rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-10 text-center shadow-[0_12px_40px_rgba(0,0,0,0.06)]">
        <p className="font-label-sm text-label-sm uppercase tracking-[0.2em] text-secondary">
          Tap&Go
        </p>
        <h1 className="font-display-lg text-4xl font-extrabold text-primary sm:text-5xl">
          {title}
        </h1>
        <p className="max-w-xl text-body-md text-on-surface-variant">{description}</p>
        <Link
          className="inline-flex items-center justify-center rounded-lg bg-secondary-container px-6 py-3 font-title-md text-title-md text-on-secondary-container transition-colors hover:bg-secondary-fixed-dim"
          to="/"
        >
          Back to Home
        </Link>
      </div>
    </main>
  )
}

export default PlaceholderPage