import { useCallback, useEffect, useRef, useState } from 'react'
import jsQR from 'jsqr'

// Camera QR scanner tuned for codes shown on screens (the POS terminal's small, glossy LCD and
// the driver web POS). Screens cause moiré and glare, and a small code held at arm's length
// covers only a few camera pixels per module, so:
//   - ask for a high-resolution stream (many phones default to 640x480 otherwise),
//   - use the browser's native BarcodeDetector when it supports QR, jsQR otherwise,
//   - each cycle try the centre crop (the guide box) at full resolution and the whole frame,
//   - scan ~7 times a second instead of every animation frame, so the page stays responsive.
// The camera is stopped whenever this component unmounts (leaving the scanner in any way).

const SCAN_INTERVAL_MS = 140
const CROP_FRACTION = 0.6        // guide box = middle 60% of the visible square
const FULL_FRAME_MAX_SIDE = 960  // jsQR full-frame pass is downscaled to keep it fast

async function createNativeDetector() {
  try {
    if (!('BarcodeDetector' in window)) return null
    const formats = await window.BarcodeDetector.getSupportedFormats()
    if (!formats.includes('qr_code')) return null
    return new window.BarcodeDetector({ formats: ['qr_code'] })
  } catch {
    return null
  }
}

async function openCamera() {
  const base = { facingMode: { ideal: 'environment' } }
  try {
    return await navigator.mediaDevices.getUserMedia({
      video: { ...base, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    })
  } catch (err) {
    // Some devices reject resolution hints outright; retry with the plain request.
    if (err?.name === 'OverconstrainedError' || err?.name === 'ConstraintNotSatisfiedError') {
      return navigator.mediaDevices.getUserMedia({ video: base, audio: false })
    }
    throw err
  }
}

function cameraErrorMessage(err) {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    return 'This browser cannot open the camera here. Use your phone camera app to scan the QR instead.'
  }
  switch (err?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Camera permission is needed to scan a QR code. Allow camera access and try again.'
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No camera was found on this device.'
    case 'NotReadableError':
      return 'The camera is being used by another app. Close it and try again.'
    default:
      return 'Could not start the camera. Use your phone camera app to scan the QR instead.'
  }
}

/**
 * Props:
 *   onDecode(text) — called with every decoded QR string. Return true when it was handled
 *                    (scanning stops); return false to keep scanning.
 */
function QrScanner({ onDecode }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const trackRef = useRef(null)
  const timerRef = useRef(null)
  const onDecodeRef = useRef(onDecode)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)
  const [torchSupported, setTorchSupported] = useState(false)
  const [torchOn, setTorchOn] = useState(false)
  const [diag, setDiag] = useState('')

  useEffect(() => {
    onDecodeRef.current = onDecode
  }, [onDecode])

  useEffect(() => {
    let cancelled = false
    let busy = false
    let detector = null
    let cycle = 0
    const cropCanvas = document.createElement('canvas')
    const fullCanvas = document.createElement('canvas')
    const cropCtx = cropCanvas.getContext('2d', { willReadFrequently: true })
    const fullCtx = fullCanvas.getContext('2d', { willReadFrequently: true })

    const stop = () => {
      window.clearTimeout(timerRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      trackRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
    }

    // Square centre crop (matches the on-screen guide box, since the video is shown object-fit: cover).
    const drawCrop = (v) => {
      const side = Math.round(Math.min(v.videoWidth, v.videoHeight) * CROP_FRACTION)
      const sx = Math.round((v.videoWidth - side) / 2)
      const sy = Math.round((v.videoHeight - side) / 2)
      if (cropCanvas.width !== side) {
        cropCanvas.width = side
        cropCanvas.height = side
      }
      cropCtx.drawImage(v, sx, sy, side, side, 0, 0, side, side)
      return cropCanvas
    }

    const jsqrOn = (canvas, ctx) => {
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
      return jsQR(img.data, img.width, img.height, { inversionAttempts: 'attemptBoth' })?.data || null
    }

    const decodeOnce = async (v) => {
      if (detector) {
        // Native detector: whole frame first (fast, handles small codes well), then the crop.
        const whole = await detector.detect(v)
        if (whole.length) return whole[0].rawValue
        const inCrop = await detector.detect(drawCrop(v))
        return inCrop.length ? inCrop[0].rawValue : null
      }
      const fromCrop = jsqrOn(drawCrop(v), cropCtx)
      if (fromCrop) return fromCrop
      // The downscaled full-frame pass is the slower one; run it every other cycle.
      if (cycle % 2) return null
      const scale = Math.min(1, FULL_FRAME_MAX_SIDE / Math.max(v.videoWidth, v.videoHeight))
      const w = Math.round(v.videoWidth * scale)
      const h = Math.round(v.videoHeight * scale)
      if (fullCanvas.width !== w || fullCanvas.height !== h) {
        fullCanvas.width = w
        fullCanvas.height = h
      }
      fullCtx.drawImage(v, 0, 0, w, h)
      return jsqrOn(fullCanvas, fullCtx)
    }

    const tick = async () => {
      if (cancelled) return
      const v = videoRef.current
      if (!busy && v && v.readyState >= v.HAVE_CURRENT_DATA && v.videoWidth > 0) {
        busy = true
        cycle += 1
        try {
          const text = await decodeOnce(v)
          if (text && !cancelled && onDecodeRef.current?.(text)) {
            stop()
            return
          }
        } catch {
          // A single failed frame (e.g. detector hiccup) must not end the scan loop.
        } finally {
          busy = false
        }
      }
      if (!cancelled) timerRef.current = window.setTimeout(tick, SCAN_INTERVAL_MS)
    }

    const start = async () => {
      try {
        const [stream, nativeDetector] = await Promise.all([openCamera(), createNativeDetector()])
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        detector = nativeDetector
        streamRef.current = stream
        const track = stream.getVideoTracks()[0]
        trackRef.current = track
        const caps = track?.getCapabilities?.() || {}
        setTorchSupported(Boolean(caps.torch))
        if (caps.focusMode?.includes?.('continuous')) {
          track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(() => {})
        }
        const v = videoRef.current
        if (!v) return
        v.setAttribute('playsinline', '') // iOS Safari: play inline, not fullscreen
        v.muted = true
        v.srcObject = stream
        await v.play()
        if (cancelled) return
        setReady(true)
        setDiag(`${v.videoWidth}×${v.videoHeight} · ${detector ? 'built-in detector' : 'jsQR'}`)
        tick()
      } catch (err) {
        if (!cancelled) setError(cameraErrorMessage(err))
        stop()
      }
    }

    start()
    return () => {
      cancelled = true
      stop()
    }
  }, [])

  const toggleTorch = useCallback(async () => {
    const track = trackRef.current
    if (!track) return
    const next = !torchOn
    try {
      await track.applyConstraints({ advanced: [{ torch: next }] })
      setTorchOn(next)
    } catch {
      setTorchSupported(false)
    }
  }, [torchOn])

  return (
    <>
      <div className="camera">
        {error ? (
          <div className="hint">{error}</div>
        ) : (
          <>
            <video ref={videoRef} autoPlay playsInline muted />
            <div className="scan-guide" aria-hidden="true" />
            {!ready && <div className="hint">Starting camera…</div>}
            {torchSupported && (
              <button type="button" className="torch" onClick={toggleTorch} aria-pressed={torchOn}>
                {torchOn ? 'Torch off' : 'Torch on'}
              </button>
            )}
          </>
        )}
      </div>
      {!error && (
        <p className="scan-tip">
          Fit the QR inside the box. On the driver&apos;s screen, tilt the phone slightly to avoid glare.
          {diag && <span className="scan-diag">{diag}</span>}
        </p>
      )}
    </>
  )
}

export default QrScanner
