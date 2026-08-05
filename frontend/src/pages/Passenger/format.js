export function vehicleLabel(type) {
  switch (type) {
    case 'Auto':
      return 'Auto Rickshaw'
    case 'Taxi':
      return 'Taxi'
    case 'topup':
      return 'Wallet Top-up'
    case 'withdraw':
      return 'Withdrawal'
    default:
      return type || 'Ride'
  }
}

export function formatRelativeTime(timestamp) {
  const diffMs = Date.now() - timestamp
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 60) return diffMins <= 1 ? 'Just now' : `${diffMins} min ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours} hr${diffHours > 1 ? 's' : ''} ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 30) return `${diffDays} days ago`
  return new Date(timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export const RANGE_OPTIONS = [
  { key: '1D', label: '1D', ms: 1000 * 60 * 60 * 24 },
  { key: '1W', label: '1W', ms: 1000 * 60 * 60 * 24 * 7 },
  { key: '1M', label: '1M', ms: 1000 * 60 * 60 * 24 * 30 },
  { key: '3M', label: '3M', ms: 1000 * 60 * 60 * 24 * 90 },
  { key: '6M', label: '6M', ms: 1000 * 60 * 60 * 24 * 180 },
  { key: '1Y', label: '1Y', ms: 1000 * 60 * 60 * 24 * 365 },
  { key: 'ALL', label: 'ALL', ms: Infinity },
]
