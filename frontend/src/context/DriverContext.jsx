import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react'
import { useAuth } from './AuthContext.jsx'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://tap-gohosting-production.up.railway.app'
const DAY = 1000 * 60 * 60 * 24

const DriverContext = createContext(null)

export function DriverProvider({ children }) {
  const { user } = useAuth()
  const [walletBalance, setWalletBalance] = useState(0)
  const [isFrozen, setIsFrozen] = useState(false)
  const [trips, setTrips] = useState([])
  const [transactions, setTransactions] = useState([])
  const [withdrawals, setWithdrawals] = useState([])
  const [reviews] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchDriverData = useCallback(async () => {
    if (!user?.id || user?.account_type !== 'driver') {
      setWalletBalance(0)
      setIsFrozen(false)
      setTrips([])
      setTransactions([])
      setWithdrawals([])
      return
    }
    setLoading(true)
    try {
      const [wRes, tRes] = await Promise.all([
        fetch(`${API_BASE}/api/wallet/${user.id}`),
        fetch(`${API_BASE}/api/wallet/${user.id}/transactions`),
      ])
      const wData = await wRes.json()
      const tData = await tRes.json()

      if (wRes.ok && wData.success && wData.wallet) {
        setWalletBalance(wData.wallet.balance)
        setIsFrozen(Boolean(wData.wallet.is_frozen))
      }

      if (tRes.ok && tData.success && Array.isArray(tData.transactions)) {
        setTransactions(tData.transactions)

        const realWithdrawals = []
        const realTrips = []

        tData.transactions.forEach((t) => {
          if (t.payment_method === 'BANK_TRANSFER' || t.payment_method === 'bank_transfer') {
            realWithdrawals.push({
              id: t.reference || `WD-${t.id}`,
              amount: t.amount,
              status: t.status === 'Completed' || t.status === 'completed' ? 'success' : t.status,
              timestamp: t.timestamp || Date.now(),
            })
          } else {
            realTrips.push({
              id: t.reference || `TRP-${t.id}`,
              passenger: t.passenger || (t.passenger_id ? `Passenger #${t.passenger_id}` : 'Passenger Ride'),
              route: t.payment_method ? `Paid via ${t.payment_method}` : 'Ride Payment',
              fare: t.amount,
              status: t.status === 'Completed' || t.status === 'completed' ? 'completed' : t.status,
              timestamp: t.timestamp || Date.now(),
            })
          }
        })

        setWithdrawals(realWithdrawals)
        setTrips(realTrips)
      }
    } catch {
      // Ignore background errors
    } finally {
      setLoading(false)
    }
  }, [user?.id, user?.account_type])

  useEffect(() => {
    fetchDriverData()
  }, [fetchDriverData])

  const completedTrips = useMemo(() => trips.filter((t) => t.status === 'completed'), [trips])
  const pendingTrips = useMemo(() => trips.filter((t) => t.status === 'pending'), [trips])
  const cancelledTrips = useMemo(() => trips.filter((t) => t.status === 'cancelled'), [trips])

  const sumFaresSince = (cutoffMs) =>
    completedTrips.filter((t) => Date.now() - t.timestamp <= cutoffMs).reduce((sum, t) => sum + t.fare, 0)

  const earnings = useMemo(
    () => ({
      today: sumFaresSince(DAY),
      week: sumFaresSince(DAY * 7),
      month: sumFaresSince(DAY * 30),
      lifetime: completedTrips.reduce((sum, t) => sum + t.fare, 0),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [completedTrips],
  )

  const rating = useMemo(() => {
    if (!reviews.length) return 5.0
    return Math.round((reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length) * 10) / 10
  }, [reviews])

  const pendingWithdrawals = useMemo(() => withdrawals.filter((w) => w.status === 'pending'), [withdrawals])
  const successfulWithdrawals = useMemo(() => withdrawals.filter((w) => w.status === 'success'), [withdrawals])

  const withdraw = async (amount) => {
    if (!user?.id || !amount || amount <= 0) return { success: false, message: 'Invalid amount' }
    try {
      const res = await fetch(`${API_BASE}/api/wallet/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, amount }),
      })
      const data = await res.json()
      if (res.ok && data.success) {
        await fetchDriverData()
        return { success: true, message: data.message }
      } else {
        return { success: false, message: data.detail || 'Withdrawal failed.' }
      }
    } catch {
      return { success: false, message: 'Backend unavailable.' }
    }
  }

  const value = useMemo(
    () => ({
      trips,
      transactions,
      completedTrips,
      pendingTrips,
      cancelledTrips,
      reviews,
      rating,
      earnings,
      walletBalance,
      isFrozen,
      withdrawals,
      pendingWithdrawals,
      successfulWithdrawals,
      loading,
      withdraw,
      refreshDriverData: fetchDriverData,
    }),
    [trips, transactions, completedTrips, pendingTrips, cancelledTrips, reviews, rating, earnings, walletBalance, isFrozen, withdrawals, pendingWithdrawals, successfulWithdrawals, loading, fetchDriverData],
  )

  return <DriverContext.Provider value={value}>{children}</DriverContext.Provider>
}

export function useDriverData() {
  const ctx = useContext(DriverContext)
  if (!ctx) throw new Error('useDriverData must be used inside a DriverProvider')
  return ctx
}
