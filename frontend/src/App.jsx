import { useEffect, useState } from 'react'
import AppRoutes from './routes/AppRoutes.jsx'
import IntroSplash from './components/Common/IntroSplash.jsx'

function App() {
  const [showIntro, setShowIntro] = useState(true)

  useEffect(() => {
    // Listen for custom event to allow replaying the intro video from anywhere
    const handleReplay = () => setShowIntro(true)
    window.addEventListener('tapgo:replay-intro', handleReplay)
    return () => window.removeEventListener('tapgo:replay-intro', handleReplay)
  }, [])

  return (
    <>
      {showIntro && <IntroSplash onFinish={() => setShowIntro(false)} />}
      <AppRoutes />
    </>
  )
}

export default App
