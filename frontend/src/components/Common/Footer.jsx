import React from 'react'
import { Link } from '../../routes/navigation.jsx'

function Footer() {
  return (
    <footer
      id="footer"
      className="mt-auto w-full border-t border-slate-200 bg-slate-900 text-slate-300 py-12"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 space-y-10">
        {/* Top Grid Section */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Col 1: Brand & Contact Info */}
          <div className="md:col-span-1 space-y-3">
            <Link to="/" className="text-2xl font-black text-white hover:opacity-90 transition-opacity">
              Tap<span className="text-amber-400">&amp;</span>Go
            </Link>
            <p className="text-xs text-slate-400 leading-relaxed font-medium">
              Smart cashless payment platform for taxis and auto-rickshaws.
            </p>
            <div className="pt-2 text-xs text-slate-300 space-y-1 font-medium">
              <p>
                <strong className="text-slate-400">Email:</strong>{' '}
                <a href="mailto:tapandgosupport@gmail.com" className="text-amber-400 hover:underline">
                  tapandgosupport@gmail.com
                </a>
              </p>
              <p>
                <strong className="text-slate-400">Support:</strong>{' '}
                <a href="tel:8779914564" className="text-slate-200 hover:underline">
                  8779914564
                </a>
              </p>
              <p className="pt-1 text-[11px] text-slate-400 leading-normal">
                <strong className="text-slate-300">Project Support Address:</strong> 7/711, Rajni Mahal, Opp. AC Market, Tardeo, Mumbai – 400034, Maharashtra, India
              </p>
            </div>
          </div>

          {/* Col 2: Quick Links */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400">Platform</h4>
            <ul className="space-y-2 text-xs font-semibold">
              <li>
                <Link to="/about" className="hover:text-amber-300 transition-colors">
                  About Us
                </Link>
              </li>
              <li>
                <Link to="/payments" className="hover:text-amber-300 transition-colors">
                  Wallet &amp; Payments
                </Link>
              </li>
              <li>
                <Link to="/pricing" className="hover:text-amber-300 transition-colors">
                  Pricing / Fare Information
                </Link>
              </li>
              <li>
                <Link to="/faq" className="hover:text-amber-300 transition-colors">
                  FAQ / Support
                </Link>
              </li>
              
            </ul>
          </div>

          {/* Col 3: Support & Assistance */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400">Support &amp; Emergency</h4>
            <ul className="space-y-2 text-xs font-semibold">
              <li>
                <Link to="/contact" className="hover:text-amber-300 transition-colors">
                  Contact Us
                </Link>
              </li>
              <li>
                <Link to="/lost-card" className="text-amber-400 hover:text-amber-300 transition-colors flex items-center gap-1 font-bold">
                  <span className="material-symbols-outlined text-sm">warning</span>
                  Lost Card Support
                </Link>
              </li>
              <li>
                <Link to="/refund-policy" className="hover:text-amber-300 transition-colors">
                  Refund &amp; Cancellation Policy
                </Link>
              </li>
              <li>
                <Link to="/shipping-policy" className="hover:text-amber-300 transition-colors">
                  Shipping &amp; Delivery Policy
                </Link>
              </li>
            </ul>
          </div>

          {/* Col 4: Legal Compliance */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400">Legal &amp; Policy</h4>
            <ul className="space-y-2 text-xs font-semibold">
              <li>
                <Link to="/privacy" className="hover:text-amber-300 transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link to="/terms" className="hover:text-amber-300 transition-colors">
                  Terms &amp; Conditions
                </Link>
              </li>
              <li>
                <Link to="/login" className="hover:text-amber-300 transition-colors">
                  Portal Login
                </Link>
              </li>
              <li>
                <Link to="/register" className="hover:text-amber-300 transition-colors">
                  Register Account
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="border-t border-slate-800 pt-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
          <p>© 2026 Tap&amp;Go. Student / Final-Year Academic Project by Moksh Gala (SVKM Bhagubai Polytechnic).</p>
          <div className="flex gap-4">
            <Link to="/privacy" className="hover:text-slate-200">Privacy</Link>
            <Link to="/terms" className="hover:text-slate-200">Terms</Link>
            <Link to="/contact" className="hover:text-slate-200">Contact</Link>
          </div>
        </div>
      </div>
    </footer>
  )
}

export default Footer
