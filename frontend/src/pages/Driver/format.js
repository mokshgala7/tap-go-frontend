export const inr = (value) =>
  `\u20b9${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(Math.round(value || 0))}`

export const inrPrecise = (value) =>
  `\u20b9${new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0)}`

export const CHART_VIEWS = [
  { key: 'week', label: 'Weekly' },
  { key: 'month', label: 'Monthly' },
  { key: 'year', label: 'Yearly' },
]

export const tripStatusLabel = {
  completed: 'Completed',
  pending: 'Pending',
  cancelled: 'Cancelled',
}
