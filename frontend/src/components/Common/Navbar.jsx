import { useState } from 'react'
import { Link, useCurrentView, useNavigate } from '../../routes/navigation.jsx'
import './Navbar.css'

const contactDetails = [
  {
    label: 'Mobile Number',
    value: '8796751324',
  },
  {
    label: 'Email',
    value: 'support@tapandgo.com',
  },
  {
    label: 'Lost Card Number',
    value: '9812567880',
  },
]

function Navbar() {
  const [isContactOpen, setIsContactOpen] = useState(false)
  const view = useCurrentView()
  const navigate = useNavigate()

  const scrollToSection = (sectionId) => {
    const scroll = () => {
      document.getElementById(sectionId)?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    }

    if (view !== 'home') {
      navigate('/')
      window.setTimeout(scroll, 80)
      return
    }

    scroll()
  }

  const handleSectionClick = (sectionId) => {
    setIsContactOpen(false)
    scrollToSection(sectionId)
  }

  const handleContactClick = () => {
    setIsContactOpen((current) => !current)
  }

  return (
    <header className="sticky top-0 z-50 border-b border-gray-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link className="text-2xl font-bold text-black" to="/" aria-label="Tap&Go home">
          Tap<span className="text-yellow-500">&amp;</span>Go
        </Link>

        <nav className="hidden gap-8 text-sm font-semibold md:flex" aria-label="Primary navigation">
          <Link to="/">Home</Link>
          <button className="tapgo-nav-link" type="button" onClick={() => handleSectionClick('features')}>
            Features
          </button>
          <button className="tapgo-nav-link" type="button" onClick={() => handleSectionClick('how')}>
            How It Works
          </button>
          <button className="tapgo-nav-link" type="button" onClick={() => handleSectionClick('why')}>
            Why Choose Us
          </button>
          <div className="tapgo-contact-menu">
            <button
              className="tapgo-nav-link tapgo-contact-trigger"
              type="button"
              onClick={handleContactClick}
              aria-expanded={isContactOpen}
              aria-controls="contact-dropdown"
            >
              Contact Us
              <span className="material-symbols-outlined" aria-hidden="true">
                expand_more
              </span>
            </button>

            {isContactOpen && (
              <div className="tapgo-contact-dropdown" id="contact-dropdown">
                {contactDetails.map((detail) => (
                  <div className="tapgo-contact-row" key={detail.label}>
                    <span>{detail.label}</span>
                    <strong>{detail.value}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </nav>

        <div className="flex gap-3">
          <Link
            className="rounded-lg border border-primary-container bg-transparent px-4 py-2 font-semibold text-primary-container"
            to="/login"
          >
            Login
          </Link>
          <Link className="rounded-lg bg-yellow-400 px-4 py-2 font-semibold text-black" to="/register">
            Register
          </Link>
        </div>
      </div>
    </header>
  )
}

export default Navbar
