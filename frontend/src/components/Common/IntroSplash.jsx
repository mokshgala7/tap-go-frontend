import { useEffect, useRef, useState } from 'react'
import './IntroSplash.css'

export default function IntroSplash({ onFinish }) {
  const [isExiting, setIsExiting] = useState(false)
  const [isMuted, setIsMuted] = useState(true)
  const [progress, setProgress] = useState(0)
  const videoRef = useRef(null)
  const exitCalledRef = useRef(false)

  const handleExit = () => {
    if (exitCalledRef.current) return
    exitCalledRef.current = true
    setIsExiting(true)
    setTimeout(() => {
      onFinish?.()
    }, 400)
  }

  // Keyboard shortcut: Escape or Space to skip immediately
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' || e.key === ' ' || e.code === 'Space') {
        e.preventDefault()
        handleExit()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Auto-play the video as soon as the component mounts
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    video.muted = true
    const playPromise = video.play()
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        console.warn('Autoplay check:', err)
        video.muted = true
        video.play().catch(() => {})
      })
    }

    // Fallback safety timer: video is ~2.04s, so 4s fallback ensures site opens even if playback stalls
    const timer = setTimeout(() => {
      handleExit()
    }, 4000)

    return () => clearTimeout(timer)
  }, [])

  const handleTimeUpdate = () => {
    const video = videoRef.current
    if (!video || !video.duration) return
    const ratio = Math.min(1, video.currentTime / video.duration)
    setProgress(ratio)
  }

  const toggleSound = () => {
    const video = videoRef.current
    if (!video) return
    const nextMuted = !video.muted
    video.muted = nextMuted
    setIsMuted(nextMuted)
  }

  return (
    <div
      className={`tapgo-intro-splash ${isExiting ? 'tapgo-intro-exiting' : ''}`}
      aria-label="Intro Video Splash"
    >
      {/* Top shadow gradient to ensure controls are easily readable */}
      <div className="tapgo-intro-top-gradient" aria-hidden="true" />

      {/* Brand Badge Top-Left */}
      <div className="tapgo-intro-badge">
        <div className="tapgo-intro-badge-title">
          Tap<span>&amp;</span>Go
        </div>
      </div>

      {/* Floating Controls Top-Right */}
      <div className="tapgo-intro-controls">
        {/* Sound Toggle Button */}
        <button
          type="button"
          className="tapgo-intro-audio-btn"
          onClick={toggleSound}
          title={isMuted ? 'Turn Sound On' : 'Mute Sound'}
          aria-label={isMuted ? 'Turn Sound On' : 'Mute Sound'}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '18px', lineHeight: 1 }}>
            {isMuted ? 'volume_off' : 'volume_up'}
          </span>
          <span className="hidden sm:inline text-xs">
            {isMuted ? 'Sound Off' : 'Sound On'}
          </span>
        </button>

        {/* Small Skip Button */}
        <button
          type="button"
          className="tapgo-intro-skip-btn"
          onClick={handleExit}
          aria-label="Skip video and open homepage"
        >
          <span>Skip</span>
          <span
            className="material-symbols-outlined"
            style={{ fontSize: '16px', lineHeight: 1 }}
            aria-hidden="true"
          >
            arrow_forward
          </span>
        </button>
      </div>

      {/* Fullscreen Video occupying entire screen */}
      <video
        ref={videoRef}
        className="tapgo-intro-video-fullscreen"
        playsInline
        autoPlay
        muted={isMuted}
        preload="auto"
        poster="/intro_poster.jpg"
        onTimeUpdate={handleTimeUpdate}
        onEnded={handleExit}
      >
        <source src="/intro_video.mp4" type="video/mp4" />
        <source src="/taxi_and_autorickshaw_like_the.mov" type="video/quicktime" />
        Your browser does not support the video tag.
      </video>

      {/* Bottom Progress Bar */}
      <div className="tapgo-intro-skip-progress-track" aria-hidden="true">
        <div
          className="tapgo-intro-skip-progress-fill"
          style={{ width: `${progress * 100}%` }}
        />
      </div>
    </div>
  )
}
