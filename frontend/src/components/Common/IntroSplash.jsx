import { useEffect, useRef, useState } from 'react'
import './IntroSplash.css'

export default function IntroSplash({ onFinish }) {
  const [isExiting, setIsExiting] = useState(false)
  const [isMuted, setIsMuted] = useState(true)
  const [progress, setProgress] = useState(0)
  const videoRef = useRef(null)
  const ambientRef = useRef(null)
  const exitCalledRef = useRef(false)

  const handleExit = () => {
    if (exitCalledRef.current) return
    exitCalledRef.current = true
    setIsExiting(true)
    setTimeout(() => {
      onFinish?.()
    }, 400)
  }

  // Keyboard shortcuts: Escape, Space, or Right Arrow to skip immediately
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' || e.key === ' ' || e.code === 'Space' || e.key === 'ArrowRight') {
        e.preventDefault()
        handleExit()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Auto-play the video as soon as the component mounts with mobile playsInline enforcement
  useEffect(() => {
    const video = videoRef.current
    const ambient = ambientRef.current
    if (!video) return

    video.muted = true
    video.defaultMuted = true
    video.setAttribute('playsinline', '')
    video.setAttribute('webkit-playsinline', '')

    if (ambient) {
      ambient.muted = true
      ambient.defaultMuted = true
      ambient.setAttribute('playsinline', '')
      ambient.setAttribute('webkit-playsinline', '')
      ambient.play().catch(() => {})
    }

    const playPromise = video.play()
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        console.warn('Intro video autoplay check:', err)
        video.muted = true
        video.play().catch(() => {})
      })
    }

    // Fallback safety timer: video is ~2.04s, so 5s fallback ensures site opens even if playback stalls
    const timer = setTimeout(() => {
      handleExit()
    }, 5000)

    return () => clearTimeout(timer)
  }, [])

  const handleTimeUpdate = () => {
    const video = videoRef.current
    if (!video || !video.duration) return
    const ratio = Math.min(1, video.currentTime / video.duration)
    setProgress(ratio)
  }

  const toggleSound = (e) => {
    e?.stopPropagation()
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
      onClick={handleExit}
    >
      {/* Ambient background blur video layer for immersive full-bleed color on any screen */}
      <video
        ref={ambientRef}
        className="tapgo-intro-ambient-video"
        playsInline
        autoPlay
        muted
        loop
        preload="auto"
        aria-hidden="true"
        poster="/intro_poster.jpg"
      >
        <source src="/intro_video.mp4" type="video/mp4" />
        <source src="/taxi_and_autorickshaw_like_the.mov" type="video/quicktime" />
      </video>

      {/* Top shadow gradient for controls visibility */}
      <div className="tapgo-intro-top-gradient" aria-hidden="true" />

      {/* Brand Badge Top-Left */}
      <div className="tapgo-intro-badge" onClick={(e) => e.stopPropagation()}>
        <div className="tapgo-intro-badge-title">
          Tap<span>&amp;</span>Go
        </div>
      </div>

      {/* Floating Controls Top-Right */}
      <div className="tapgo-intro-controls" onClick={(e) => e.stopPropagation()}>
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
          <span className="tapgo-intro-audio-label text-xs">
            {isMuted ? 'Sound Off' : 'Sound On'}
          </span>
        </button>

        {/* Skip Button */}
        <button
          type="button"
          className="tapgo-intro-skip-btn"
          onClick={handleExit}
          aria-label="Skip video and open site"
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

      {/* Centered Video Container with Proper Containment & Framing for Mobile & Desktop */}
      <div className="tapgo-intro-video-container" onClick={(e) => e.stopPropagation()}>
        <video
          ref={videoRef}
          className="tapgo-intro-video-element"
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
      </div>

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
