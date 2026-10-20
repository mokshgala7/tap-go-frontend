import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
// Phone-only look aligned with the Flutter app (white / yellow / black). Must load last.
import './styles/mobile-tailwind.css'
import './styles/mobile-app.css'
import './styles/mobile-inline.css'
import { startMobileTableLabels } from './utils/mobileTableLabels.js'
import { startMobileEmoji } from './utils/mobileEmoji.js'
import { NavProvider } from './routes/navigation.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { WalletProvider } from './context/WalletContext.jsx'
import { DriverProvider } from './context/DriverContext.jsx'

startMobileTableLabels()
startMobileEmoji()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <NavProvider>
      <AuthProvider>
        <WalletProvider>
          <DriverProvider>
            <App />
          </DriverProvider>
        </WalletProvider>
      </AuthProvider>
    </NavProvider>
  </StrictMode>,
)
