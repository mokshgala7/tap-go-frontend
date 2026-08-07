import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from '../../routes/navigation.jsx'
import DemoInfoBanner from '../../components/Common/DemoInfoBanner.jsx'
import DemoInfoCard from '../../components/Common/DemoInfoCard.jsx'
import '../../styles/AuthPages.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://tap-go-backend.onrender.com'

const patterns = {
  name: /^[a-zA-Z\s]{3,}$/,
  email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  phone: /^[0-9]{10}$/,
  pincode: /^[0-9]{6}$/,
  aadhaar: /^[0-9]{12}$/,
  emailOtp: /^[0-9]{6}$/,
  pan: /^[A-Z]{5}[0-9]{4}[A-Z]$/,
  vehicleReg: /^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$/,
  dl: /^[A-Z]{2}[0-9]{13}$/,
}

const initialForm = {
  accountType: 'passenger',
  name: 'Rohan Sharma',
  email: 'rohan.sharma@example.com',
  phone: '9876543210',
  address: '405, Shivam Towers, J.G. Road, Bandra West',
  city: 'Mumbai',
  pincode: '400050',
  aadhaar: '987654321012',
  emailOtp: '',
  pan: 'ABCDE1234F',
  password: 'Rohan@123',
  confirmPassword: 'Rohan@123',
  vehicleType: '',
  vehicleReg: '',
  vehicleMake: '',
  vehicleModel: '',
  dl: '',
  terms: true,
}

const fieldLabels = {
  name: 'Full Name',
  email: 'Email Address',
  phone: 'Mobile Number',
  address: 'Complete Address',
  city: 'City',
  pincode: 'Pincode',
  aadhaar: 'Aadhaar Number',
  emailOtp: '6-Digit Email OTP',
  pan: 'PAN Card Number',
  password: 'Create Password',
  confirmPassword: 'Confirm Password',
  vehicleReg: 'Registration No (e.g. MH01AB1234)',
  vehicleMake: 'Manufacturer (e.g. Tata)',
  vehicleModel: 'Model (e.g. Nexon EV)',
  dl: 'Driving Licence Number',
}

const errorText = {
  name: 'Min 3 characters, letters only.',
  email: 'Enter a valid email.',
  phone: 'Must be exactly 10 digits.',
  address: 'Address is required.',
  city: 'City is required.',
  pincode: 'Must be 6 digits.',
  aadhaar: 'Must be 12 digits.',
  emailOtp: 'Must be 6 digits.',
  pan: 'Format: ABCDE1234F',
  password: 'Use at least 8 chars with letters and numbers.',
  confirmPassword: 'Passwords do not match.',
  vehicleType: 'Required.',
  vehicleReg: 'Invalid Format.',
  vehicleMake: 'Required.',
  vehicleModel: 'Required.',
  dl: 'Invalid format.',
}

function CheckIcon({ className = 'w-6 h-6' }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
    </svg>
  )
}

function LineIcon({ children, className = 'w-5 h-5' }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      {children}
    </svg>
  )
}

function FloatingInput({
  name,
  value,
  onChange,
  touched,
  valid,
  type = 'text',
  maxLength,
  className = '',
  as = 'input',
}) {
  const Component = as

  return (
    <div className="relative group">
      <div className="relative">
        <Component
          className={`peer input-premium ${as === 'textarea' ? 'input-premium-textarea' : ''} ${valid ? 'input-valid' : ''} ${touched && !valid ? 'input-invalid' : ''} ${className}`}
          id={name}
          name={name}
          type={type}
          rows={as === 'textarea' ? 2 : undefined}
          placeholder=" "
          maxLength={maxLength}
          value={value}
          onChange={onChange}
        />
        <label
          className={`floating-label ${as === 'textarea' ? '!top-3 !text-[0.65rem] !font-bold !text-gray-500 !uppercase !tracking-wide' : ''}`}
          htmlFor={name}
        >
          {fieldLabels[name]}
        </label>
        {valid && (
          <div className={`validation-icon absolute right-5 ${as === 'textarea' ? 'top-8' : 'top-1/2 -translate-y-1/2'} transform text-success animate-scale-in`}>
            <CheckIcon />
          </div>
        )}
      </div>
      {touched && !valid && <p className="error-msg">{errorText[name]}</p>}
    </div>
  )
}

function FileUpload({ label, helper, file, onChange, error, preview }) {
  return (
    <div className="relative">
      <label
        className={`upload-zone w-full flex flex-col items-center justify-center p-10 rounded-2xl cursor-pointer relative overflow-hidden group/upload ${file ? 'upload-success' : ''}`}
      >
        <input className="hidden" type="file" accept="image/*,.pdf" onChange={onChange} />
        {preview && (
          <div
            className="absolute inset-0 bg-cover bg-center z-10 transition-transform duration-700 group-hover/upload:scale-105"
            style={{ backgroundImage: `url(${preview})` }}
          >
            <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center opacity-0 group-hover/upload:opacity-100 transition-opacity duration-400 backdrop-blur-sm">
              <span className="text-white text-[0.85rem] font-bold tracking-widest uppercase">Change Photo</span>
            </div>
          </div>
        )}
        <div className={`${preview ? 'hidden' : 'flex'} flex-col items-center transition-transform duration-500 group-hover/upload:scale-105`}>
          <div className="w-20 h-20 rounded-full bg-brand/15 text-brand flex items-center justify-center mb-5">
            <LineIcon className="w-10 h-10">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </LineIcon>
          </div>
          <span className="text-[0.95rem] font-bold text-gray-800 tracking-wide">
            {label} <span className="text-brand underline decoration-[3px] underline-offset-4">Browse</span>
          </span>
          <span className="text-xs text-gray-400 mt-3 font-semibold uppercase tracking-widest">{helper}</span>
        </div>
      </label>
      {error && <p className="error-msg">{error}</p>}
    </div>
  )
}

function ProgressCheck({ active, hidden, label }) {
  if (hidden) return null
  return (
    <div className={`check-item rounded-xl p-3 flex items-center gap-3 ${active ? 'active' : ''}`}>
      <div className="w-5 h-5 rounded-full flex items-center justify-center check-icon">
        <CheckIcon className="w-3 h-3" />
      </div>
      <span className="text-gray-300">{label}</span>
    </div>
  )
}

function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState(initialForm)
  const [touched, setTouched] = useState({})
  const [profilePhoto, setProfilePhoto] = useState(null)   // Face photo — shown in live preview
  const [files, setFiles] = useState({ rc: null, dlUpload: null, insurance: null, idDoc: null })
  const [signature, setSignature] = useState(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [otpVerified, setOtpVerified] = useState(false)  // True once OTP is verified on-the-spot
  const [otpSending, setOtpSending] = useState(false)
  const [otpMessage, setOtpMessage] = useState('')       // Status message for OTP
  const [otpVerifying, setOtpVerifying] = useState(false)
  const [legalModal, setLegalModal] = useState(null)     // null | 'terms' | 'privacy' | 'esign'
  const canvasRef = useRef(null)
  const [sessionId] = useState(() => Math.floor(100000 + Math.random() * 900000))
  const [sessionTime] = useState(() => {
    const now = new Date()
    return `SECURE SESSION • ${now.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })} • ${now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}`
  })

  // Restore form data from sessionStorage when returning from review page
  useEffect(() => {
    const stored = sessionStorage.getItem('registrationReviewData')
    if (stored) {
      try {
        const data = JSON.parse(stored)
        if (data.form) setForm({ ...initialForm, ...data.form })
        if (data.profilePhoto) setProfilePhoto(data.profilePhoto)
        if (data.signature) setSignature(data.signature)
        if (data.files) setFiles(prev => ({ ...prev, ...data.files }))
      } catch (e) {
        // ignore parse errors
      }
    }
  }, [])

  const passwordStrength = useMemo(() => {
    let strength = 0
    if (form.password.length > 0) strength = 1
    if (form.password.length >= 8) strength = 2
    if (form.password.length >= 8 && /[A-Za-z]/.test(form.password) && /[0-9]/.test(form.password)) strength = 3
    if (form.password.length >= 8 && /[A-Z]/.test(form.password) && /[a-z]/.test(form.password) && /[0-9]/.test(form.password) && /[^A-Za-z0-9]/.test(form.password)) strength = 4
    return strength
  }, [form.password])

  const valid = useMemo(
    () => ({
      name: patterns.name.test(form.name.trim()),
      email: patterns.email.test(form.email.trim()),
      phone: patterns.phone.test(form.phone),
      address: form.address.trim().length > 0,
      city: form.city.trim().length > 0,
      pincode: patterns.pincode.test(form.pincode),
      aadhaar: patterns.aadhaar.test(form.aadhaar),
      emailOtp: otpVerified,  // Must be verified on-the-spot, not just 6 digits
      pan: patterns.pan.test(form.pan),
      password: passwordStrength >= 3,
      confirmPassword: form.confirmPassword.length > 0 && form.confirmPassword === form.password && passwordStrength >= 3,
      vehicleType: form.vehicleType.length > 0,
      vehicleReg: patterns.vehicleReg.test(form.vehicleReg),
      vehicleMake: form.vehicleMake.trim().length > 0,
      vehicleModel: form.vehicleModel.trim().length > 0,
      dl: patterns.dl.test(form.dl),
    }),
    [form, passwordStrength, otpVerified],
  )

  const isDriver = form.accountType === 'driver'
  const allValid = useMemo(() => {
    const base = [
      valid.name,
      valid.email,
      valid.phone,
      valid.address,
      valid.city,
      valid.pincode,
      valid.aadhaar,
      valid.emailOtp,    // OTP is required
      valid.pan,
      valid.password,
      valid.confirmPassword,
      Boolean(profilePhoto),
      Boolean(signature),
      form.terms,
    ]
    const driver = [valid.vehicleType, valid.vehicleReg, valid.vehicleMake, valid.vehicleModel, valid.dl, files.rc, files.dlUpload, files.insurance]
    return [...base, ...(isDriver ? driver : [])].every(Boolean)
  }, [valid, profilePhoto, signature, form.terms, isDriver, files])

  const progress = useMemo(() => {
    const base = [
      valid.name,
      valid.email,
      valid.phone,
      valid.address,
      valid.city,
      valid.pincode,
      valid.aadhaar,
      valid.emailOtp,
      valid.pan,
      valid.password,
      valid.confirmPassword,
      Boolean(profilePhoto),
      Boolean(signature),
      form.terms,
    ]
    const driver = [valid.vehicleType, valid.vehicleReg, valid.vehicleMake, valid.vehicleModel, valid.dl, files.rc, files.dlUpload, files.insurance]
    const items = [...base, ...(isDriver ? driver : [])]
    return Math.round((items.filter(Boolean).length / items.length) * 100)
  }, [valid, profilePhoto, signature, form.terms, isDriver, files])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const rect = canvas.parentElement.getBoundingClientRect()
      canvas.width = rect.width
      canvas.height = 220
      const ctx = canvas.getContext('2d')
      ctx.lineJoin = 'round'
      ctx.lineCap = 'round'
      ctx.lineWidth = 3.5
      ctx.strokeStyle = '#000000'
      if (signature) {
        const img = new Image()
        img.src = signature
        img.onload = () => ctx.drawImage(img, 0, 0)
      }
    }
    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [signature])

  const updateForm = (event) => {
    const { name, value, type, checked } = event.target
    let nextValue = type === 'checkbox' ? checked : value
    if (['phone', 'pincode', 'aadhaar', 'emailOtp'].includes(name)) nextValue = value.replace(/\D/g, '')
    if (['pan', 'vehicleReg', 'dl'].includes(name)) nextValue = value.toUpperCase()
    setForm((current) => ({ ...current, [name]: nextValue }))

    // If email changes, reset OTP verification
    if (name === 'email') {
      setOtpVerified(false)
      setOtpMessage('')
    }
  }

  // Auto-verify OTP on the spot when 6 digits are entered
  useEffect(() => {
    const otp = form.emailOtp
    if (otp.length === 6 && /^[0-9]{6}$/.test(otp) && !otpVerified && form.email) {
      setOtpVerifying(true)
      setOtpMessage('')
      fetch(`${API_BASE}/api/auth/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: form.email, otp })
      })
        .then(res => res.json().then(data => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          setOtpVerifying(false)
          if (ok && data.success) {
            setOtpVerified(true)
            setOtpMessage('✓ Email verified!')
          } else {
            setOtpVerified(false)
            setOtpMessage(data.detail || 'Invalid OTP')
          }
        })
        .catch(() => {
          setOtpVerifying(false)
          setOtpMessage('Verification failed')
        })
    }
    if (otp.length < 6) {
      setOtpVerified(false)
      setOtpMessage('')
    }
  }, [form.emailOtp, form.email, otpVerified])

  const handleFile = (key, event) => {
    const file = event.target.files?.[0]
    if (!file) return

    // Profile face photo — shown as avatar in live preview
    if (key === 'profilePhoto') {
      if (!file.type.startsWith('image/')) {
        alert('Please upload an image file (JPG, PNG, WebP).')
        return
      }
      const reader = new FileReader()
      reader.onload = (e) => setProfilePhoto(e.target.result)
      reader.readAsDataURL(file)
      return
    }

    // All other docs (idDoc, rc, dlUpload, insurance) stored in files state
    const reader = new FileReader()
    reader.onload = (loadEvent) => {
      setFiles((current) => ({
        ...current,
        [key]: {
          name: file.name,
          type: file.type || 'application/octet-stream',
          dataUrl: loadEvent.target.result,
        },
      }))
    }
    reader.readAsDataURL(file)
  }

  const getCanvasPos = (event) => {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const point = event.touches?.[0] || event
    return { x: point.clientX - rect.left, y: point.clientY - rect.top }
  }

  const startDraw = (event) => {
    event.preventDefault()
    const ctx = canvasRef.current.getContext('2d')
    const pos = getCanvasPos(event)
    ctx.beginPath()
    ctx.moveTo(pos.x, pos.y)
    setIsDrawing(true)
  }

  const draw = (event) => {
    if (!isDrawing) return
    event.preventDefault()
    const ctx = canvasRef.current.getContext('2d')
    const pos = getCanvasPos(event)
    ctx.lineTo(pos.x, pos.y)
    ctx.stroke()
  }

  const endDraw = () => {
    if (!isDrawing) return
    setIsDrawing(false)
    setSignature(canvasRef.current.toDataURL('image/png'))
  }

  const clearSignature = () => {
    const canvas = canvasRef.current
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height)
    setSignature(null)
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!allValid) {
      setTouched(
        Object.keys(valid).reduce((next, key) => {
          next[key] = true
          return next
        }, {}),
      )
      // Give specific feedback on what's missing
      const missing = []
      if (!valid.confirmPassword && form.confirmPassword.length > 0 && form.confirmPassword !== form.password) {
        missing.push('Passwords do not match.')
      }
      if (!otpVerified) missing.push('Please verify your email with the OTP.')
      if (!profilePhoto) missing.push('Please upload your profile photo.')
      if (!signature) missing.push('Please draw your digital signature.')
      if (missing.length) alert(missing.join('\n'))
      return
    }
    setLoading(true)
    window.setTimeout(() => {
      setLoading(false)
      sessionStorage.setItem(
        'registrationReviewData',
        JSON.stringify({
          form,
          profilePhoto,
          signature,
          files,
          sessionId,
          isDriver,
        }),
      )
      navigate('/registration-review')
    }, 900)
  }

  const ringOffset = 289 - (289 * progress) / 100
  const strengthColors = ['bg-gray-200', 'bg-error', 'bg-warning', 'bg-info', 'bg-success']
  const strengthText = ['Not Started', 'Weak', 'Medium', 'Strong', 'Very Strong']

  return (
    <div className="auth-page bg-surface text-[#1C1C1E] selection:bg-brand selection:text-darker overflow-x-hidden antialiased">
      <div className="flex flex-col lg:flex-row min-h-screen lg:h-screen lg:overflow-hidden relative w-full">
        <aside className="desktop-id-wrap lg:w-[45%] lg:h-screen lg:overflow-y-auto hide-scrollbar bg-darker text-white p-0 lg:p-10 flex flex-col items-center z-40 relative">
          <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
            <div className="absolute top-[-15%] left-[-15%] w-[70%] h-[70%] rounded-full bg-brand opacity-[0.08] blur-[140px] animate-ambient"></div>
            <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] rounded-full bg-blue-600 opacity-[0.06] blur-[120px] animate-ambient"></div>
          </div>

          <div className="glass-panel w-full max-w-xl lg:rounded-[3rem] p-6 lg:p-8 relative z-10 shadow-[0_30px_60px_rgba(0,0,0,0.6)] flex flex-col gap-5 min-h-full lg:min-h-0 lg:my-auto shrink-0">
            <div className="flex justify-between items-start">
              <div className="space-y-2">
                <div className="text-[0.65rem] tracking-[0.25em] text-brand font-black uppercase mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-brand animate-pulse shadow-[0_0_10px_rgba(253,211,77,1)]"></span>
                  Live Preview
                </div>
                <h1 className="text-3xl lg:text-4xl font-black tracking-tighter bg-clip-text text-transparent bg-gradient-to-br from-white via-gray-200 to-gray-500 drop-shadow-sm">
                  Tap&Go Identity
                </h1>
                <div className="flex items-center gap-4 mt-4">
                  <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold tracking-wide transition-all duration-500 backdrop-blur-md ${isDriver ? 'badge-pro' : 'bg-white/5 text-gray-300 border border-white/10'}`}>
                    {isDriver ? 'Professional Driver' : 'Passenger'}
                  </div>
                  <span className="text-xs text-gray-500 font-mono font-semibold tracking-wider">ID: T&G-{sessionId}</span>
                </div>
              </div>
              <div className="relative w-24 h-24 lg:w-28 lg:h-28 flex items-center justify-center">
                <svg className="absolute inset-0 w-full h-full transform -rotate-90 drop-shadow-glow" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="8"></circle>
                  <circle cx="50" cy="50" r="46" fill="none" stroke={progress === 100 ? '#00C853' : '#FDD34D'} strokeWidth="8" strokeDasharray="289" strokeDashoffset={ringOffset} strokeLinecap="round"></circle>
                </svg>
                <div className="text-center">
                  <span className="text-2xl lg:text-3xl font-black text-white block leading-none">{progress}%</span>
                  <span className="text-[0.6rem] tracking-widest text-brand font-bold uppercase block mt-1.5">Score</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col lg:flex-row items-center lg:items-start gap-5 py-5 border-y border-white/5 relative">
              <div className="relative group z-10">
                <div className="w-24 h-24 lg:w-28 lg:h-28 rounded-full bg-darker/60 border-2 border-white/10 flex items-center justify-center overflow-hidden transition-all duration-700 bg-cover bg-center shadow-inner-light" style={{ backgroundImage: profilePhoto ? `url(${profilePhoto})` : undefined }}>
                  {!profilePhoto && (
                    <LineIcon className="w-14 h-14 text-gray-600">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </LineIcon>
                  )}
                </div>
                {profilePhoto && (
                  <div className="absolute bottom-1 right-1 w-10 h-10 bg-[#00C853] rounded-full border-[3px] border-darker flex items-center justify-center shadow-[0_0_20px_rgba(0,200,83,0.6)] z-20">
                    <CheckIcon className="w-6 h-6 text-white" />
                  </div>
                )}
              </div>
              <div className="text-center lg:text-left w-full flex-1 space-y-2 z-10">
                <h2 className={`text-3xl font-black truncate transition-colors duration-500 tracking-tight ${form.name ? 'text-white' : 'text-gray-500'}`}>{form.name || 'New User'}</h2>
                <p className="text-sm font-medium text-gray-500 truncate opacity-80">{form.email || '-'}</p>
                <p className="text-[0.95rem] text-gray-500 truncate font-mono mt-1 opacity-80">{form.phone ? `+91 ${form.phone}` : '-'}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-5 z-10">
              <div className="glass-card-inner rounded-3xl p-5">
                <p className="text-[0.65rem] text-gray-400 uppercase tracking-widest mb-3 font-bold">Location</p>
                <p className="text-[0.9rem] font-semibold truncate text-gray-500 leading-tight">{form.address || '-'}</p>
                <p className="text-xs text-gray-500 mt-1.5 truncate opacity-80">{form.city || form.pincode ? `${form.city}${form.city && form.pincode ? ', ' : ''}${form.pincode}` : '-'}</p>
              </div>
              <div className="glass-card-inner rounded-3xl p-5">
                <p className="text-[0.65rem] text-gray-400 uppercase tracking-widest mb-3 font-bold flex justify-between items-center">
                  Govt ID <span className={`px-2 py-0.5 rounded text-[0.6rem] ${valid.aadhaar && valid.pan ? 'text-[#00C853] bg-[#00C853]/10' : 'text-[#FF3B30] bg-[#FF3B30]/10'}`}>{valid.aadhaar && valid.pan ? 'Verified' : 'Pending'}</span>
                </p>
                <p className="text-xs font-mono tracking-widest truncate text-gray-500 mb-1.5">{valid.aadhaar ? `XXXX XXXX ${form.aadhaar.slice(-4)}` : form.aadhaar || '-'}</p>
                <p className="text-xs font-mono tracking-widest truncate text-gray-500 uppercase">{form.pan || '-'}</p>
              </div>
            </div>

            {isDriver && (
              <div className="glass-card-inner rounded-3xl p-6 bg-brand/5 border-brand/20 relative overflow-hidden group">
                <p className="text-[0.65rem] text-brand uppercase tracking-widest mb-4 font-black">Vehicle & Licence</p>
                <div className="grid grid-cols-2 gap-5 relative z-10">
                  <div>
                    <p className="text-[0.95rem] font-bold truncate text-gray-500 mb-1.5">{`${form.vehicleMake} ${form.vehicleModel} ${form.vehicleType ? `(${form.vehicleType})` : ''}`.trim() || '-'}</p>
                    <p className="text-xs font-mono text-gray-500 truncate uppercase">{form.vehicleReg || '-'}</p>
                  </div>
                  <div>
                    <p className="text-[0.6rem] text-gray-500 uppercase tracking-widest mb-1 font-bold">Licence No</p>
                    <p className="text-xs font-mono text-gray-500 truncate uppercase">{form.dl || '-'}</p>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3 relative z-10 mt-5 pt-5 border-t border-white/10">
                  {[
                    ['rc', 'RC Book'],
                    ['dlUpload', 'Licence'],
                    ['insurance', 'Insurance'],
                  ].map(([key, label]) => (
                    <div key={key}>
                      <p className="text-[0.6rem] text-gray-400 uppercase tracking-widest mb-1 font-bold flex items-center gap-1">
                        {label}
                        {files[key] && <CheckIcon className="w-3 h-3 text-success" />}
                      </p>
                      <p className={`text-[0.7rem] truncate font-semibold ${files[key] ? 'text-gray-300' : 'text-gray-600'}`}>{files[key]?.name || 'Not uploaded'}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-4 z-10">
              <div className="flex justify-between items-end mb-4">
                <p className="text-[0.65rem] text-gray-400 uppercase tracking-widest font-bold">Verification Checklist</p>
                <p className="text-[0.65rem] text-brand font-bold bg-brand/10 px-2.5 py-1 rounded-md">{progress === 100 ? 'Ready' : `Est. ${Math.max(1, Math.ceil(5 - progress / 20))} mins`}</p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs font-semibold">
                <ProgressCheck active={valid.name} label="Personal" />
                <ProgressCheck active={valid.email && valid.phone} label="Contact" />
                <ProgressCheck active={valid.address && valid.city && valid.pincode} label="Address" />
                <ProgressCheck active={valid.aadhaar && valid.pan} label="Aadhaar & PAN" />
                <ProgressCheck active={Boolean(profilePhoto)} label="Photo" />
                <ProgressCheck active={valid.emailOtp} label="OTP Verified" />
                <ProgressCheck active={Boolean(signature)} label="Signature" />
                <ProgressCheck active={valid.vehicleType && valid.vehicleReg && valid.vehicleMake && valid.vehicleModel} hidden={!isDriver} label="Vehicle" />
                <ProgressCheck active={valid.dl && files.rc && files.dlUpload && files.insurance} hidden={!isDriver} label="Driver Docs" />
              </div>
            </div>

            <div className={`glass-card-inner rounded-3xl p-4 relative h-[90px] shrink-0 flex items-center justify-center overflow-hidden group z-10 transition-all duration-500 border ${signature ? 'bg-white/10 border-[#00C853]/40' : 'border-white/5'}`}>
              <div className="absolute top-4 left-5 right-5 flex justify-between items-center z-10">
                <p className={`text-[0.6rem] uppercase tracking-widest font-bold ${signature ? 'text-success' : 'text-gray-500'}`}>{signature ? 'Signed Digitally' : 'E-Signature Pending'}</p>
              </div>
              {signature ? <img src={signature} className="h-16 mt-5 object-contain filter invert opacity-90" alt="Signature" /> : <span className="text-gray-600 text-sm">Signature preview</span>}
            </div>

            <div className="w-full text-center z-10 shrink-0">
              <p className="text-[0.6rem] text-gray-600 font-mono tracking-widest">{sessionTime}</p>
            </div>
          </div>
        </aside>

        <main className="form-wrap w-full lg:w-[55%] bg-surface flex flex-col items-center py-12 lg:py-24 px-5 sm:px-10 lg:px-20 min-h-screen lg:h-screen lg:overflow-y-auto relative z-10">
          <div className="w-full max-w-2xl lg:max-w-3xl">
            <div className="mb-14 text-center lg:text-left">
              <Link to="/" className="inline-flex mb-6 text-sm font-black uppercase tracking-widest text-gray-400 hover:text-darker">Back Home</Link>
              <h2 className="text-4xl lg:text-[3.5rem] font-black text-darker tracking-tighter mb-4 leading-none">Create Account</h2>
              <p className="text-[#8E8E93] text-base lg:text-lg font-medium tracking-wide">Join the secure cashless ecosystem with Tap&Go.</p>
            </div>

            <div className="mb-8">
              <DemoInfoCard type="database" />
            </div>

            <form className="space-y-10" noValidate onSubmit={handleSubmit}>
              <div className="bg-white p-2.5 rounded-[1.25rem] shadow-card-border">
                <div className="flex">
                  {['passenger', 'driver'].map((type) => (
                    <div className="flex-1 relative" key={type}>
                      <input className="segment-radio sr-only" type="radio" id={type} name="accountType" value={type} checked={form.accountType === type} onChange={updateForm} />
                      <label htmlFor={type} className="flex items-center justify-center gap-2.5 w-full py-4 text-[0.95rem] font-bold text-gray-500 rounded-xl cursor-pointer transition-all duration-400 capitalize">
                        {type}
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              <section className="form-section-card space-y-7">
                <h3 className="section-title">Personal Details</h3>

                {/* Profile Face Photo Uploader */}
                <div>
                  <p className="text-xs font-black uppercase tracking-widest text-darker mb-3">Your Profile Photo</p>
                  <label className={`group relative flex items-center gap-5 p-4 rounded-2xl border-2 cursor-pointer transition-all duration-300 ${
                    profilePhoto ? 'border-[#00C853] bg-[#F0FDF4]' : 'border-dashed border-gray-300 bg-gray-50 hover:border-brand hover:bg-[#FFFCF5]'
                  }`}>
                    <input className="hidden" type="file" accept="image/*" onChange={(e) => handleFile('profilePhoto', e)} />
                    <div className={`w-20 h-20 rounded-full border-4 flex-shrink-0 overflow-hidden flex items-center justify-center transition-all duration-500 ${
                      profilePhoto ? 'border-[#00C853] shadow-[0_0_20px_rgba(0,200,83,0.3)]' : 'border-gray-200 bg-white'
                    }`} style={{ backgroundImage: profilePhoto ? `url(${profilePhoto})` : undefined, backgroundSize: 'cover', backgroundPosition: 'center' }}>
                      {!profilePhoto && (
                        <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      )}
                    </div>
                    <div className="flex-1">
                      <p className={`font-bold text-sm mb-1 transition-colors ${profilePhoto ? 'text-[#166534]' : 'text-gray-700'}`}>
                        {profilePhoto ? '✓ Photo uploaded — visible in live preview' : 'Click to upload your face photo'}
                      </p>
                      <p className="text-xs text-gray-400 font-semibold uppercase tracking-wide">
                        {profilePhoto ? 'Tap to change' : 'JPG, PNG, WebP • Max 5MB • Clear face photo required'}
                      </p>
                    </div>
                    {profilePhoto && (
                      <div className="w-9 h-9 bg-[#00C853] rounded-full flex items-center justify-center flex-shrink-0 shadow-[0_0_15px_rgba(0,200,83,0.4)]">
                        <CheckIcon className="w-5 h-5 text-white" />
                      </div>
                    )}
                  </label>
                  {touched.profilePhoto && !profilePhoto && <p className="error-msg">Profile photo is required.</p>}
                </div>

                <FloatingInput name="name" value={form.name} onChange={updateForm} touched={touched.name} valid={valid.name} />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <FloatingInput name="email" type="email" value={form.email} onChange={updateForm} touched={touched.email} valid={valid.email} />
                    </div>
                  </div>
                  <div>
                    <div className="flex gap-2 items-center">
                      <div className="flex-1">
                        <FloatingInput name="emailOtp" maxLength={6} value={form.emailOtp} onChange={updateForm} touched={touched.emailOtp} valid={otpVerified} className={`tracking-[0.5em] font-mono font-bold ${otpVerified ? 'text-[#00C853]' : 'text-brand'}`} />
                      </div>
                      <button type="button" disabled={otpSending || !valid.email || otpVerified} onClick={async () => {
                        if (!valid.email) return
                        setOtpSending(true)
                        setOtpMessage('')
                        setOtpVerified(false)
                        try {
                          const res = await fetch(`${API_BASE}/api/auth/send-otp`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ email: form.email, account_type: form.accountType })
                          })
                          const data = await res.json()
                          setOtpSending(false)
                          if (res.ok && data.success) {
                            if (data.demo_mode && data.otp) {
                              // Demo mode: email delivery restricted, OTP returned directly
                              setOtpMessage(`📋 Demo Mode — Your OTP is: ${data.otp} (copy & paste it above)`)
                              // Auto-fill the OTP field for convenience
                              updateForm({ target: { name: 'emailOtp', value: data.otp } })
                            } else {
                              setOtpMessage('OTP sent! Check your inbox.')
                            }
                          } else {
                            setOtpMessage(data.detail || 'Failed to send OTP.')
                          }
                        } catch (err) {
                          setOtpSending(false)
                          setOtpMessage('Error connecting to server.')
                        }
                      }} className={`h-[60px] px-3 sm:px-5 font-black rounded-xl transition whitespace-nowrap text-xs sm:text-sm tracking-wide border-2 ${
                        otpVerified
                          ? 'bg-[#00C853] text-white border-[#00C853] cursor-default'
                          : otpSending
                            ? 'bg-gray-200 text-gray-500 border-gray-200 cursor-wait'
                            : 'bg-white text-darker border-brand hover:bg-brand hover:text-darker shadow-sm'
                      }`}>
                        {otpVerified ? '✓ Verified' : otpSending ? 'Sending...' : 'Send OTP'}
                      </button>
                    </div>
                    {/* OTP status message */}
                    {otpMessage && (
                      <p className={`text-xs font-bold mt-2 px-1 ${otpVerified ? 'text-[#00C853]' : otpMessage.includes('Demo Mode') ? 'text-[#d97706]' : 'text-[#FF3B30]'}`}>
                        {otpVerifying ? '⏳ Verifying...' : otpMessage}
                      </p>
                    )}
                    {otpVerifying && !otpMessage && (
                      <p className="text-xs font-bold mt-2 px-1 text-brand">⏳ Verifying OTP...</p>
                    )}
                  </div>
                  <FloatingInput name="phone" type="tel" maxLength={10} value={form.phone} onChange={updateForm} touched={touched.phone} valid={valid.phone} />
                </div>
                <div className="pt-2">
                  <DemoInfoCard type="otp" />
                </div>
              </section>

              <section className="form-section-card space-y-7">
                <h3 className="section-title">Address</h3>
                <FloatingInput as="textarea" name="address" value={form.address} onChange={updateForm} touched={touched.address} valid={valid.address} />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
                  <FloatingInput name="city" value={form.city} onChange={updateForm} touched={touched.city} valid={valid.city} />
                  <FloatingInput name="pincode" maxLength={6} value={form.pincode} onChange={updateForm} touched={touched.pincode} valid={valid.pincode} />
                </div>
              </section>

              <section className="form-section-card space-y-7 !border-2 !border-brand/30 !bg-[#FFFCF5]">
                <div className="absolute top-0 right-0 bg-gradient-to-l from-brand to-[#F59E0B] text-darker text-[0.6rem] font-black px-5 py-2 rounded-bl-2xl rounded-tr-[1.25rem] uppercase tracking-widest shadow-md">Mandatory Govt Verification</div>
                <h3 className="section-title !text-darker">Identity Setup</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
                  <FloatingInput name="aadhaar" maxLength={12} value={form.aadhaar} onChange={updateForm} touched={touched.aadhaar} valid={valid.aadhaar} className="tracking-widest font-mono text-lg" />
                </div>
                <FloatingInput name="pan" maxLength={10} value={form.pan} onChange={updateForm} touched={touched.pan} valid={valid.pan} className="uppercase font-mono tracking-widest text-lg" />
                {/* ID Document upload — Aadhaar card / PAN card image */}
                <FileUpload
                  label="Upload Aadhaar / PAN Card Image"
                  helper="JPEG, PNG, PDF • Max 5MB"
                  file={files.idDoc}
                  preview={files.idDoc?.dataUrl && files.idDoc.type?.startsWith('image/') ? files.idDoc.dataUrl : null}
                  onChange={(event) => handleFile('idDoc', event)}
                  error={touched.idDoc && !files.idDoc ? 'Government ID document is required.' : ''}
                />
              </section>

              <section className={`driver-section ${isDriver ? 'active' : ''}`}>
                <div className="driver-inner form-section-card space-y-7 !bg-[#F4F4F5] !border-none">
                  <div className="absolute top-0 right-0 bg-darker text-brand text-[0.6rem] font-black px-5 py-2 rounded-bl-2xl rounded-tr-[1.5rem] uppercase tracking-widest shadow-md">Professional Driver</div>
                  <h3 className="section-title !text-darker">Vehicle & Documentation</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
                    <div className="relative group">
                      <select className={`peer input-premium appearance-none ${valid.vehicleType ? 'input-valid' : ''}`} name="vehicleType" value={form.vehicleType} onChange={updateForm}>
                        <option value="" disabled>Select Category</option>
                        <option>Auto Rickshaw</option>
                        <option>Taxi</option>
                        <option>Sedan</option>
                        <option>SUV</option>
                        <option>Mini Cab</option>
                        <option>EV Taxi</option>
                        <option>Luxury Taxi</option>
                      </select>
                      <label className="floating-label !top-2 !text-[0.65rem] !font-bold !text-gray-500 !uppercase">Vehicle Type</label>
                    </div>
                    <FloatingInput name="vehicleReg" maxLength={10} value={form.vehicleReg} onChange={updateForm} touched={touched.vehicleReg} valid={valid.vehicleReg} className="uppercase font-mono tracking-widest text-lg" />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
                    <FloatingInput name="vehicleMake" value={form.vehicleMake} onChange={updateForm} touched={touched.vehicleMake} valid={valid.vehicleMake} />
                    <FloatingInput name="vehicleModel" value={form.vehicleModel} onChange={updateForm} touched={touched.vehicleModel} valid={valid.vehicleModel} />
                  </div>
                  <FloatingInput name="dl" maxLength={15} value={form.dl} onChange={updateForm} touched={touched.dl} valid={valid.dl} className="uppercase font-mono tracking-widest text-lg" />
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5 pt-4">
                    {[
                      ['rc', 'RC Book'],
                      ['dlUpload', 'Licence'],
                      ['insurance', 'Insurance'],
                    ].map(([key, label]) => (
                      <label key={key} className={`upload-zone w-full flex flex-col items-center justify-center py-6 px-4 rounded-2xl cursor-pointer relative overflow-hidden group/doc h-36 ${files[key] ? 'upload-success' : ''}`}>
                        <input className="hidden" type="file" accept=".pdf,image/*" onChange={(event) => handleFile(key, event)} />
                        <span className="text-[0.75rem] font-bold uppercase tracking-widest text-gray-700 z-10 mb-1.5">{label}</span>
                        <span className="text-[0.65rem] text-gray-400 font-semibold uppercase tracking-widest z-10 text-center truncate w-full px-2">{files[key]?.name || 'Upload PDF/Img'}</span>
                        {files[key] && <CheckIcon className="w-6 h-6 text-success absolute top-4 right-4" />}
                      </label>
                    ))}
                  </div>
                </div>
              </section>

              <section className="form-section-card space-y-7">
                <h3 className="section-title">Security</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-7">
                  <div>
                    <FloatingInput name="password" type="password" value={form.password} onChange={updateForm} touched={touched.password} valid={valid.password} className="tracking-widest font-mono text-lg" />
                    <div className="flex gap-2 mt-4">
                      {[0, 1, 2, 3].map((item) => (
                        <div key={item} className={`h-2 flex-1 rounded-full transition-all duration-500 ${item < passwordStrength ? strengthColors[passwordStrength] : 'bg-gray-200'}`}></div>
                      ))}
                    </div>
                    <div className="flex justify-between items-center mt-3 bg-gray-50 p-3 rounded-lg border border-gray-100">
                      <span className="text-[0.7rem] font-black uppercase tracking-widest text-gray-400">{strengthText[passwordStrength]}</span>
                      <span className="text-[0.65rem] text-gray-500 font-semibold tracking-wide">Aa + 123 + #$& (Min 8)</span>
                    </div>
                  </div>
                  <FloatingInput name="confirmPassword" type="password" value={form.confirmPassword} onChange={updateForm} touched={touched.confirmPassword} valid={valid.confirmPassword} className="tracking-widest font-mono text-lg" />
                </div>
                <label className="flex items-start gap-4 cursor-pointer group pt-4">
                  <div className="relative mt-1">
                    <input className="peer sr-only" type="checkbox" name="terms" checked={form.terms} onChange={updateForm} />
                    <div className="w-7 h-7 border-2 border-gray-300 bg-white rounded-lg peer-checked:bg-darker peer-checked:border-darker transition-all duration-400"></div>
                    {form.terms && <CheckIcon className="absolute inset-1 w-5 h-5 text-brand" />}
                  </div>
                  <div className="text-[0.95rem] text-gray-600 font-medium leading-relaxed">
                    I accept the{' '}
                    <button type="button" onClick={() => setLegalModal('terms')} className="text-darker font-bold underline decoration-brand decoration-2 underline-offset-4 hover:text-brand transition-colors">Terms &amp; Conditions</button>,{' '}
                    <button type="button" onClick={() => setLegalModal('privacy')} className="text-darker font-bold underline decoration-brand decoration-2 underline-offset-4 hover:text-brand transition-colors">Privacy Policy</button>{' '}
                    and legally bind myself to the{' '}
                    <button type="button" onClick={() => setLegalModal('esign')} className="text-darker font-bold underline decoration-brand decoration-2 underline-offset-4 hover:text-brand transition-colors">Electronic Signature Agreement</button>.
                  </div>
                </label>

                <div className="pt-6 border-t border-gray-200">
                  <div className="flex justify-between items-end mb-5">
                    <label className="block text-xs font-black uppercase tracking-widest text-darker">Digital Authorization Signature</label>
                    <button type="button" onClick={clearSignature} className="text-[0.7rem] text-error hover:bg-red-50 uppercase font-bold tracking-widest px-4 py-2 rounded-xl bg-white border border-red-100 shadow-sm transition-colors">Clear</button>
                  </div>
                  <div className="relative rounded-2xl overflow-hidden group/sig bg-white shadow-sm">
                    <canvas
                      ref={canvasRef}
                      className="signature-canvas w-full h-[220px] block"
                      onMouseDown={startDraw}
                      onMouseMove={draw}
                      onMouseUp={endDraw}
                      onMouseLeave={endDraw}
                      onTouchStart={startDraw}
                      onTouchMove={draw}
                      onTouchEnd={endDraw}
                    ></canvas>
                    {!signature && !isDrawing && (
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none transition-opacity duration-400">
                        <span className="bg-gray-100 text-gray-400 text-sm font-bold px-6 py-3 rounded-full shadow-sm tracking-wide">Draw signature here</span>
                      </div>
                    )}
                  </div>
                  {touched.signature && !signature && <p className="error-msg">Valid signature is required to proceed.</p>}
                </div>
              </section>

              <div className="pt-10 pb-24 relative">
                <button className="btn-primary w-full py-6 rounded-[1.5rem] font-black text-xl tracking-wide flex items-center justify-center gap-4 relative overflow-hidden group" type="submit" disabled={loading}>
                  <span className="relative z-10">{loading ? 'Processing Identity...' : allValid ? 'Review Account' : 'Complete All Fields'}</span>
                  {loading && <div className="spinner relative z-10 border-[4px]"></div>}
                </button>
                <p className="mt-6 text-center text-sm font-bold text-gray-500">
                  Already registered? <Link className="text-darker underline decoration-brand decoration-2 underline-offset-4" to="/login">Back to Login</Link>
                </p>
              </div>
            </form>
          </div>
        </main>

        {/* Legal Modal */}
        {legalModal && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(6px)' }}
            onClick={() => setLegalModal(null)}
          >
            <div
              className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between px-8 py-6 border-b border-gray-100 bg-[#1C1C1E] rounded-t-3xl">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[3px] text-[#FDD34D] mb-1">
                    Tap&amp;Go Legal
                  </div>
                  <h2 className="text-white font-black text-xl tracking-tight">
                    {legalModal === 'terms' && 'Terms & Conditions'}
                    {legalModal === 'privacy' && 'Privacy Policy'}
                    {legalModal === 'esign' && 'Electronic Signature Agreement'}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setLegalModal(null)}
                  className="w-10 h-10 rounded-full bg-white/10 text-white hover:bg-white/20 transition flex items-center justify-center text-xl font-bold"
                >
                  ×
                </button>
              </div>
              {/* Gold bar */}
              <div style={{ height: 4, background: 'linear-gradient(90deg,#FDD34D,#F59E0B)' }} />
              {/* Scrollable content */}
              <div className="overflow-y-auto px-8 py-6 text-[0.92rem] text-gray-700 leading-relaxed space-y-5 flex-1">
                {legalModal === 'terms' && (
                  <>
                    <p><strong>Last updated:</strong> August 2026</p>
                    <p>Welcome to <strong>Tap&amp;Go</strong>. By registering an account, you agree to the following terms and conditions in their entirety.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">1. Service Description</h3>
                    <p>Tap&amp;Go is a smart transit payment platform that facilitates cashless fare collection between passengers and registered drivers. The platform operates via NFC/QR-based transactions and digital wallets.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">2. Eligibility</h3>
                    <p>You must be at least 18 years of age and a resident of India to register. By registering, you confirm that all information provided is accurate and complete.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">3. Account Responsibility</h3>
                    <p>You are solely responsible for maintaining the confidentiality of your login credentials. Tap&amp;Go is not liable for losses arising from unauthorized account access.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">4. Payments & Wallet</h3>
                    <p>All wallet top-ups and payments are processed through authorized payment gateways. Refunds are subject to our refund policy and may take 5–7 business days.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">5. Prohibited Activities</h3>
                    <p>You agree not to misuse the platform for fraudulent transactions, unauthorized access, or any activity that violates applicable Indian laws.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">6. Termination</h3>
                    <p>Tap&amp;Go reserves the right to suspend or terminate accounts found in violation of these terms without prior notice.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">7. Governing Law</h3>
                    <p>These terms are governed by the laws of India. Any disputes shall be subject to the exclusive jurisdiction of courts in Mumbai, Maharashtra.</p>
                  </>
                )}
                {legalModal === 'privacy' && (
                  <>
                    <p><strong>Last updated:</strong> August 2026</p>
                    <p>Your privacy is important to us. This policy explains how Tap&amp;Go collects, uses, and protects your personal information.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">1. Information We Collect</h3>
                    <p>We collect your name, email, phone number, Aadhaar number, PAN card, address, profile photo, and uploaded documents for identity verification purposes.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">2. How We Use Your Information</h3>
                    <p>Your information is used to: verify your identity, process payments, provide customer support, detect fraud, and comply with legal obligations under Indian law.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">3. Data Sharing</h3>
                    <p>We do not sell your personal data. We may share data with payment processors (e.g. PayU), regulatory authorities, and fraud prevention services as required.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">4. Data Security</h3>
                    <p>All data is encrypted in transit (TLS 1.3) and at rest. Passwords are hashed using bcrypt. Sensitive documents are stored on secured servers.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">5. Your Rights</h3>
                    <p>You have the right to access, update, or request deletion of your personal data. Contact us at support@tapandgo.app to exercise these rights.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">6. Cookies</h3>
                    <p>We use session cookies for authentication purposes only. We do not use tracking or advertising cookies.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">7. Contact</h3>
                    <p>For privacy concerns, contact our Data Protection Officer at <strong>privacy@tapandgo.app</strong>.</p>
                  </>
                )}
                {legalModal === 'esign' && (
                  <>
                    <p><strong>Last updated:</strong> August 2026</p>
                    <p>By drawing your digital signature on this registration form, you agree to the following Electronic Signature Agreement.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">1. Legal Validity</h3>
                    <p>Your digital signature drawn on this form constitutes a legally binding electronic signature under the <strong>Information Technology Act, 2000</strong> of India and has the same legal effect as a handwritten signature.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">2. Consent to Electronic Records</h3>
                    <p>You consent to receive all agreements, notices, disclosures, and communications electronically. You confirm you have the ability to access and retain electronic records.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">3. Signature Binding</h3>
                    <p>By submitting this form with your drawn signature, you acknowledge that you have read and agree to all terms, and that this signature binds you to the Tap&amp;Go Terms &amp; Conditions and Privacy Policy.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">4. Signature Storage</h3>
                    <p>Your signature image is stored securely on our servers and linked to your account for audit and compliance purposes. It will not be shared with third parties except as required by law.</p>
                    <h3 className="font-black text-[#1C1C1E] text-base">5. Right to Withdraw</h3>
                    <p>You may withdraw your consent to electronic signatures by contacting support@tapandgo.app. However, withdrawal will require account deactivation as e-signature is mandatory for platform compliance.</p>
                  </>
                )}
              </div>
              {/* Footer button */}
              <div className="px-8 py-5 border-t border-gray-100 bg-gray-50 rounded-b-3xl">
                <button
                  type="button"
                  onClick={() => setLegalModal(null)}
                  className="w-full py-4 rounded-2xl font-black text-sm tracking-widest uppercase bg-[#1C1C1E] text-white hover:bg-[#FDD34D] hover:text-[#1C1C1E] transition-all duration-300"
                >
                  I Understand — Close
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}

export default Register
