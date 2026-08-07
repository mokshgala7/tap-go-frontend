import { Link } from '../../routes/navigation.jsx'
import Footer from '../../components/Common/Footer.jsx'
import Navbar from '../../components/Common/Navbar.jsx'
import DemoInfoBanner from '../../components/Common/DemoInfoBanner.jsx'
import logo from '../../assets/images/logio.png'
import './Home.css'

const features = [
  {
    icon: 'contactless',
    iconClass: 'bg-primary-container text-on-primary shadow-sm',
    glowClass: 'bg-secondary-container/10 group-hover:bg-secondary-container/20',
    title: 'Instant Cashless Payments',
    description:
      'Complete payments instantly using NFC or QR codes, eliminating the need for cash while ensuring a smooth travel experience.',
  },
  {
    icon: 'security',
    iconClass: 'bg-surface-container-highest text-primary border border-outline-variant shadow-sm',
    glowClass: 'bg-primary/5 group-hover:bg-primary/10',
    title: 'AI Fraud Detection',
    description:
      'Advanced AI continuously analyzes transactions to detect suspicious activity and help protect both passengers and drivers.',
  },
  {
    icon: 'account_balance_wallet',
    iconClass: 'bg-primary-container text-on-primary shadow-sm',
    glowClass: 'bg-secondary-container/10 group-hover:bg-secondary-container/20',
    title: 'Digital Wallet',
    description:
      'Securely manage your wallet, view transaction history, track balances, and access digital receipts-all in one place.',
  },
]

const steps = [
  {
    number: '1️⃣',
    title: 'Register',
    description: 'Create your passenger or driver account.',
  },
  {
    number: '2️⃣',
    title: 'Login',
    description: 'Securely access your dashboard.',
  },
  {
    number: '3️⃣',
    title: 'Scan QR / Tap NFC',
    description: 'Choose your preferred payment method.',
  },
  {
    number: '4️⃣',
    title: 'Pay Securely',
    description: 'AI verifies every transaction.',
  },
  {
    number: '5️⃣',
    title: 'Done!',
    description: 'Receive instant confirmation and receipt.',
  },
]

const benefits = [
  {
    title: 'AI Security',
    description: 'Fraud detection helps protect every transaction.',
  },
  {
    title: 'Instant Payments',
    description: 'Fast QR and NFC transactions in seconds.',
  },
  {
    title: 'Digital Wallet',
    description: 'Track balances and payment history easily.',
  },
  {
    title: 'Built for Mobility',
    description: 'Designed specifically for taxis and auto-rickshaws.',
  },
]

function Home() {
  return (
    <div className="tapgo-home tapgo-shell bg-surface text-on-surface font-body-lg antialiased selection:bg-secondary-container selection:text-on-secondary-container">
      <Navbar />
      <DemoInfoBanner />

      <main className="min-h-screen flex flex-col items-center justify-center pb-section-gap pt-8">
        <section className="mx-auto flex w-full max-w-7xl flex-col items-center space-y-12 px-container-padding text-center">
          <div className="relative w-full max-w-4xl">
            <img
              alt="Tap&Go Mobility logo"
              className="mx-auto h-auto w-full max-w-3xl object-contain"
              src={logo}
            />
          </div>

          <div className="max-w-3xl space-y-6">
            <h1 className="sr-only">Smart Payments. Every Ride.</h1>

            <div className="mx-auto max-w-2xl space-y-3 text-on-surface-variant">
              <p className="font-body-lg text-body-lg">
                <strong>Fast. Secure. Cashless Travel Payments.</strong>
              </p>
              <p className="p2">
                Experience the future of transportation payments with <strong>Tap&Go</strong>.
                Our platform enables passengers to pay taxi and auto-rickshaw fares instantly
                using <strong>NFC</strong> or <strong>QR codes</strong>, while providing drivers
                with secure digital payments, real-time transaction tracking, and AI-powered
                fraud detection.
              </p>
            </div>

            <div className="flex flex-col items-center justify-center gap-gutter pt-4 sm:flex-row">
              <Link
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-primary-container bg-transparent px-8 py-4 text-title-md font-title-md text-primary-container sm:w-auto"
                to="/login"
              >
                Log in
                <span className="material-symbols-outlined" aria-hidden="true">
                  arrow_forward
                </span>
              </Link>

              <Link
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-yellow-400 px-8 py-4 text-title-md font-title-md text-black sm:w-auto"
                to="/register"
              >
                Register
              </Link>
            </div>
          </div>
        </section>

        <section
          id="features"
          className="relative mt-24 w-full max-w-7xl border-t border-surface-variant px-container-padding py-24"
        >
          <div className="absolute inset-0 -z-10 bg-gradient-to-b from-surface-container-lowest to-surface"></div>

          <div className="mb-16 text-center">
            <h3 className="mb-4 text-center text-4xl font-bold">Feautures</h3>
            <h2 className="font-headline-lg text-headline-lg text-primary mb-4">
              Designed for Safe and Seamless Payments
            </h2>
            <p className="font-body-md text-body-md mx-auto max-w-xl text-on-surface-variant">
              Built specifically for taxis and auto-rickshaws, Tap&Go delivers fast
              transactions, secure authentication, and an effortless payment experience for every
              ride.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-gutter md:grid-cols-3">
            {features.map((feature) => (
              <article
                key={feature.title}
                className="group relative flex flex-col items-start overflow-hidden rounded-xl border border-outline-variant/30 bg-surface-container-lowest p-8 shadow-[0_4px_12px_rgba(0,0,0,0.03)] transition-all duration-300 hover:shadow-[0_12px_32px_rgba(0,0,0,0.06)]"
              >
                <div
                  className={`absolute right-0 top-0 -mr-16 -mt-16 h-32 w-32 rounded-full blur-3xl transition-colors ${feature.glowClass}`}
                ></div>
                <div
                  className={`mb-6 flex h-12 w-12 items-center justify-center rounded-lg ${feature.iconClass}`}
                >
                  <span className="material-symbols-outlined material-symbols-filled" aria-hidden="true">
                    {feature.icon}
                  </span>
                </div>
                <h3 className="font-title-md text-title-md mb-3 text-primary">{feature.title}</h3>
                <p className="font-body-md text-body-md leading-relaxed text-on-surface-variant">
                  {feature.description}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section id="how" className="mx-auto w-full max-w-7xl px-6 py-24">
          <h2 className="mb-4 text-center text-4xl font-bold">How Tap&Go Works</h2>
          <p className="mb-12 text-center text-gray-600">Getting started is simple and takes only a few seconds.</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6 text-center">
            {steps.map((step) => (
              <article key={step.title}>
                <div className="text-5xl">{step.number}</div>
                <h3 className="mt-3 font-bold">{step.title}</h3>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="why" className="w-full bg-gray-50 py-24">
          <div className="mx-auto max-w-7xl px-6">
            <h2 className="mb-12 text-center text-4xl font-bold">Why Choose Tap&Go?</h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {benefits.map((benefit) => (
                <article key={benefit.title} className="rounded-xl bg-white p-6 shadow">
                  <h3 className="font-bold">{benefit.title}</h3>
                  <p>{benefit.description}</p>
                </article>
              ))}
            </div>

            <div className="mt-16 text-center">
              <h3 className="mb-4 text-3xl font-bold">Ready to Experience Smarter Travel?</h3>
              <p className="mb-6 text-gray-600">
                Join Tap&Go today and enjoy fast, secure and cashless transportation payments.
              </p>
              <Link className="rounded-lg bg-yellow-400 px-8 py-4 font-bold text-black" to="/register">
                Register Now
              </Link>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  )
}

export default Home
