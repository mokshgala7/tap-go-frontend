import React, { useState, useEffect } from 'react'
import { useNavigate } from '../routes/navigation.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function RegistrationReview() {
  const navigate = useNavigate()
  const { register } = useAuth()
  const [formData, setFormData] = useState(null)
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Get form data from sessionStorage
    const storedData = sessionStorage.getItem('registrationReviewData')
    if (storedData) {
      try {
        const data = JSON.parse(storedData)
        setFormData(data)
      } catch (error) {
        console.error('Failed to parse registration data:', error)
        navigate('/register')
      }
    } else {
      navigate('/register')
    }
    setLoading(false)
  }, [navigate])

  const [errorMessage, setErrorMessage] = useState('')

  const dataURLtoFile = (dataurl, filename) => {
    if (!dataurl || typeof dataurl !== 'string' || !dataurl.includes(',')) return null
    try {
      const arr = dataurl.split(',')
      const mimeMatch = arr[0].match(/:(.*?);/)
      const mime = mimeMatch ? mimeMatch[1] : 'image/png'
      const bstr = atob(arr[1])
      let n = bstr.length
      const u8arr = new Uint8Array(n)
      while (n--) {
        u8arr[n] = bstr.charCodeAt(n)
      }
      return new File([u8arr], filename, { type: mime })
    } catch (e) {
      return null
    }
  }

  const confirmAccount = async () => {
    setConfirming(true)
    setErrorMessage('')

    const { form, profilePhoto, files, signature } = formData

    const payload = new FormData()
    payload.append('account_type', form.accountType || 'passenger')
    payload.append('name', form.name || '')
    payload.append('email', form.email || '')
    payload.append('phone', form.phone || '')
    payload.append('address', form.address || '')
    payload.append('city', form.city || '')
    payload.append('pincode', form.pincode || '')
    payload.append('aadhaar', form.aadhaar || '')
    payload.append('email_otp', form.emailOtp || '')
    payload.append('pan', form.pan || '')
    payload.append('password', form.password || '')

    if (form.accountType === 'driver') {
      payload.append('vehicle_type', form.vehicleType || '')
      payload.append('vehicle_registration', form.vehicleReg || '')
      payload.append('vehicle_make', form.vehicleMake || '')
      payload.append('vehicle_model', form.vehicleModel || '')
      payload.append('driving_licence_number', form.dl || '')
    }

    // Profile face photo
    if (profilePhoto) {
      const photoFile = dataURLtoFile(profilePhoto, 'profile_photo.png')
      if (photoFile) payload.append('photo', photoFile)
    }

    // Government ID document (Aadhaar / PAN card image)
    if (files?.idDoc?.dataUrl) {
      const idFile = dataURLtoFile(files.idDoc.dataUrl, files.idDoc.name || 'id_document.jpg')
      if (idFile) payload.append('id_doc', idFile)
    }

    // Digital signature — canvas PNG
    if (signature) {
      const sigFile = dataURLtoFile(signature, 'digital_signature.png')
      if (sigFile) payload.append('signature', sigFile)
    }

    if (files?.rc?.dataUrl) {
      const rcFile = dataURLtoFile(files.rc.dataUrl, files.rc.name || 'rc_document.pdf')
      if (rcFile) payload.append('rc', rcFile)
    }

    if (files?.dlUpload?.dataUrl) {
      const dlFile = dataURLtoFile(files.dlUpload.dataUrl, files.dlUpload.name || 'licence_document.pdf')
      if (dlFile) payload.append('licence', dlFile)
    }

    if (files?.insurance?.dataUrl) {
      const insFile = dataURLtoFile(files.insurance.dataUrl, files.insurance.name || 'insurance_document.pdf')
      if (insFile) payload.append('insurance', insFile)
    }

    const res = await register(payload)
    setConfirming(false)

    if (res.success) {
      sessionStorage.removeItem('registrationReviewData')
      navigate('/login')
    } else {
      setErrorMessage(res.message || 'Registration failed')
    }
  }

  const editDetails = () => {
    navigate('/register')
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="text-center">
          <div className="spinner"></div>
          <p className="mt-4 text-gray-500 font-medium">Loading your details...</p>
        </div>
      </div>
    )
  }

  if (!formData) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 font-medium">No registration data found.</p>
          <button onClick={() => navigate('/register')} className="mt-4 btn-primary px-6 py-3 rounded-lg">
            Back to Registration
          </button>
        </div>
      </div>
    )
  }

  const { form, profilePhoto, signature, sessionId, isDriver } = formData

  return (
    <div className="bg-surface text-[#1C1C1E] selection:bg-brand selection:text-darker min-h-screen antialiased">
      <div className="w-full max-w-6xl mx-auto p-6 lg:p-16 min-h-screen flex flex-col relative">
        {/* Header */}
        <div className="flex items-center justify-between mb-12 pb-8 border-b border-gray-200 relative z-10">
          <div>
            <h2 className="text-4xl lg:text-[3rem] font-black text-darker tracking-tighter mb-2">Review Application</h2>
            <p className="text-gray-500 font-medium text-lg tracking-wide">Please verify your details before final submission.</p>
          </div>
          <div className="px-6 py-3 bg-white text-brand text-[0.8rem] font-black rounded-full uppercase tracking-widest border border-brand/30 shadow-[0_4px_12px_rgba(253,211,77,0.2)]">
            Final Step
          </div>
        </div>

        {/* Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 relative z-10">
          {/* Left Column */}
          <div className="space-y-10">
            {/* Profile Section */}
            <div className="bg-white p-8 rounded-[2rem] border border-gray-100 shadow-premium flex items-center gap-8 relative overflow-hidden">
              <div className="w-32 h-32 rounded-full border-[6px] border-white shadow-[0_8px_24px_rgba(0,0,0,0.1)] overflow-hidden bg-gray-50 relative z-10">
                {profilePhoto ? (
                  <img src={profilePhoto} className="w-full h-full object-cover" alt="Profile" />
                ) : (
                  <div className="w-full h-full bg-gray-100 flex items-center justify-center text-4xl font-black text-gray-300">
                    {form.name.charAt(0)}
                  </div>
                )}
              </div>
              <div>
                <h3 className="text-3xl font-black text-darker tracking-tight mb-2">{form.name}</h3>
                <p className={`text-[0.7rem] font-black uppercase tracking-widest inline-block px-4 py-1.5 rounded-lg ${isDriver ? 'text-darker bg-brand' : 'text-gray-500 bg-gray-100'}`}>
                  {isDriver ? 'Professional Driver' : 'Passenger'}
                </p>
                <p className="text-[0.75rem] text-gray-400 font-mono mt-3 font-semibold tracking-wider">T&G-{sessionId}</p>
              </div>
            </div>

            {/* Personal Details */}
            <div className="bg-white p-8 rounded-[2rem] shadow-sm border border-gray-100 space-y-6 text-[0.95rem] font-medium">
              <div className="flex items-center justify-between pb-4 border-b border-gray-100/50">
                <span className="text-gray-400">Email</span>
                <span className="text-darker font-semibold">{form.email}</span>
              </div>
              <div className="flex items-center justify-between pb-4 border-b border-gray-100/50">
                <span className="text-gray-400">Phone</span>
                <span className="text-darker font-mono font-semibold">+91 {form.phone}</span>
              </div>
              <div className="flex items-start justify-between pt-1">
                <span className="text-gray-400">Address</span>
                <span className="text-darker font-semibold text-right max-w-[60%] leading-relaxed">
                  {form.address}, {form.city} - {form.pincode}
                </span>
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-10">
            {/* Government ID */}
            <div className="bg-white p-8 rounded-[2rem] shadow-sm border border-gray-100 space-y-6 text-[0.95rem] font-medium relative overflow-hidden">
              <div className="absolute right-0 top-0 h-full w-2 bg-success"></div>
              <div className="flex items-center justify-between pb-4 border-b border-gray-100/50">
                <span className="text-gray-400">Aadhaar</span>
                <span className="text-darker font-mono tracking-widest font-semibold">XXXX XXXX {form.aadhaar.slice(-4)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">PAN</span>
                <span className="text-darker font-mono uppercase tracking-widest font-semibold">{form.pan}</span>
              </div>
            </div>

            {/* Vehicle Details (Driver Only) */}
            {isDriver && (
              <div className="bg-white p-8 rounded-[2rem] shadow-premium border border-brand/20 space-y-6 text-[0.95rem] font-medium">
                <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                  <span className="text-gray-400">Vehicle Type</span>
                  <span className="text-darker font-black text-lg">{form.vehicleType}</span>
                </div>
                <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                  <span className="text-gray-400">Make & Model</span>
                  <span className="text-darker font-semibold">
                    {form.vehicleMake} {form.vehicleModel}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-400">Licence No.</span>
                  <span className="text-darker font-mono uppercase tracking-widest font-bold">{form.dl}</span>
                </div>
              </div>
            )}

            {/* Signature Preview */}
            <div className="bg-white p-8 rounded-[2rem] border border-gray-100 flex flex-col items-center justify-center h-[240px] relative overflow-hidden shadow-sm">
              {signature ? (
                <img src={signature} className="h-32 max-w-full object-contain mix-blend-multiply mt-6" alt="Signature" />
              ) : (
                <span className="text-gray-400 text-sm font-medium">Signature preview</span>
              )}
            </div>
          </div>
        </div>

        {/* Verification Checklist */}
        <div className="mt-16 p-8 bg-white rounded-[2rem] border border-gray-100 shadow-sm relative z-10">
          <h3 className="text-lg font-black text-darker mb-6 tracking-tight">Verification Checklist</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              'Personal Information Verified',
              'Contact Details Valid',
              'Government ID Provided',
              'Address Confirmed',
              isDriver ? 'Vehicle Details Provided' : 'Account Type Selected',
              'Digital Signature Captured',
              'Terms & Conditions Accepted',
              'All Required Fields Completed',
            ].map((item, index) => (
              <div key={index} className="flex items-center gap-3">
                <div className="w-5 h-5 rounded-full bg-success flex items-center justify-center flex-shrink-0">
                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <span className="text-gray-700 font-medium text-sm">{item}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Action Buttons */}
        {errorMessage && (
          <div className="mt-6 p-4 bg-red-50 border border-red-200 text-red-600 rounded-xl text-center font-bold text-sm">
            {errorMessage}
          </div>
        )}
        <div className="mt-10 pt-10 flex flex-col md:flex-row gap-6 border-t border-gray-200 relative z-10 pb-10">
          <button
            type="button"
            onClick={editDetails}
            className="px-10 py-6 rounded-[1.5rem] font-bold text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 hover:text-darker transition-colors w-full md:w-[35%] tracking-wide shadow-sm text-lg"
          >
            Edit Details
          </button>
          <button
            type="button"
            onClick={confirmAccount}
            disabled={confirming}
            className="flex-1 btn-primary py-6 rounded-[1.5rem] font-black text-xl tracking-wide group relative overflow-hidden disabled:opacity-75"
          >
            <span className="relative z-10 block">{confirming ? 'Account Created' : 'Confirm & Create Account'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}

export default RegistrationReview
