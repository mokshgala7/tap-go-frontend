import Admin from '../pages/Admin/Admin.jsx'
import Driver from '../pages/Driver/Driver.jsx'
import ForgotPassword from '../pages/ForgotPassword/ForgotPassword.jsx'
import Home from '../pages/Home/Home.jsx'
import Login from '../pages/Login.jsx'
import Passenger from '../pages/Passenger/Passenger.jsx'
import Register from '../pages/Register/Register.jsx'
import RegistrationReview from '../pages/RegistrationReview.jsx'
import ReadmePage from '../pages/ReadmePage.jsx'
import { useCurrentView } from './navigation.jsx'

// Tap&Go is a single-page app: this is the only place that decides what's
// on screen. There is no browser routing and no other URL ever works -
// swapping "view" in NavProvider is the only way the visible page changes.
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
    case 'readme':
      return <ReadmePage />
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
