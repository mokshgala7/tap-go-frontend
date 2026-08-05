import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { NavProvider } from './routes/navigation.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { WalletProvider } from './context/WalletContext.jsx'
import { DriverProvider } from './context/DriverContext.jsx'

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
