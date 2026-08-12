import Admin from '../pages/Admin/Admin.jsx'
import Driver from '../pages/Driver/Driver.jsx'
import ForgotPassword from '../pages/ForgotPassword/ForgotPassword.jsx'
import Home from '../pages/Home/Home.jsx'
import Login from '../pages/Login.jsx'
import Passenger from '../pages/Passenger/Passenger.jsx'
import Register from '../pages/Register/Register.jsx'
import RegistrationReview from '../pages/RegistrationReview.jsx'

// Compliance & Informational Pages
import AboutUs from '../pages/AboutUs.jsx'
import ContactUs from '../pages/ContactUs.jsx'
import PrivacyPolicy from '../pages/PrivacyPolicy.jsx'
import TermsConditions from '../pages/TermsConditions.jsx'
import RefundPolicy from '../pages/RefundPolicy.jsx'
import ShippingPolicy from '../pages/ShippingPolicy.jsx'
import PricingInfo from '../pages/PricingInfo.jsx'
import PaymentInfo from '../pages/PaymentInfo.jsx'
import LostCardSupport from '../pages/LostCardSupport.jsx'
import FaqSupport from '../pages/FaqSupport.jsx'

import { useCurrentView } from './navigation.jsx'

function AppRoutes() {
  const view = useCurrentView()

  switch (view) {
    case 'login':
      return <Login />
    case 'register':
      return <Register />
    case 'registration-review':
      return <RegistrationReview />
    case 'forgot-password':
      return <ForgotPassword />
    case 'about':
      return <AboutUs />
    case 'contact':
      return <ContactUs />
    case 'privacy':
      return <PrivacyPolicy />
    case 'terms':
      return <TermsConditions />
    case 'refund-policy':
      return <RefundPolicy />
    case 'shipping-policy':
      return <ShippingPolicy />
    case 'pricing':
      return <PricingInfo />
    case 'payments':
      return <PaymentInfo />
    case 'lost-card':
      return <LostCardSupport />
    case 'faq':
      return <FaqSupport />
    case 'passenger':
      return <Passenger />
    case 'driver':
      return <Driver />
    case 'admin':
      return <Admin />
    case 'home':
    default:
      return <Home />
  }
}

export default AppRoutes
