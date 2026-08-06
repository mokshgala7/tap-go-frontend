import { useEffect, useState } from 'react'
import { adminRequest } from '../api.js'

const RESOURCES = [
  ['Drivers', '/users?account_type=driver'],
  ['Passengers', '/users?account_type=passenger'],
  ['Transactions', '/transactions'],
  ['Wallets', '/wallets'],
  ['Documents', '/documents'],
  ['Edit Requests', '/edit-requests'],
  ['Admins', '/activity-logs'],
]

function cell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export default function DatabaseViewer({ adminId }) {
  const [selected, setSelected] = useState(RESOURCES[0])
  const [search, setSearch] = useState('')
  const [result, setResult] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    const targetLabel = selected?.[0] || RESOURCES[0][0]
    const targetPath = selected?.[1] || RESOURCES[0][1]
    const params = search.trim() && ['Drivers', 'Passengers', 'Transactions', 'Wallets', 'Documents'].includes(targetLabel) ? `&search=${encodeURIComponent(search.trim())}` : ''
    const fullPath = `${targetPath}${targetPath.includes('?') ? params : `?${params.replace(/^&/, '')}`}`

    adminRequest(fullPath, adminId)
      .then((data) => {
        if (alive) {
          setResult(data && typeof data === 'object' ? data : { items: [], total: 0 })
          setLoading(false)
        }
      })
      .catch((requestError) => {
        if (alive) {
          setError(requestError?.message || 'Failed to load database records.')
          setLoading(false)
        }
      })
    return () => { alive = false }
  }, [adminId, selected, search])

  const items = Array.isArray(result?.items) ? result.items : []
  const fields = Object.keys(items[0] || {}).filter((key) => !['proof_path', 'file_path'].includes(key))

  return (
    <section className="admin-section">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Internal developer tool</span>
          <h2>Database Viewer</h2>
          <p>Read-only, paginated access to the live MySQL records through FastAPI.</p>
        </div>
      </div>
      <div className="database-toolbar">
        <select
          value={selected?.[0] || RESOURCES[0][0]}
          onChange={(event) => {
            const found = RESOURCES.find(([label]) => label === event.target.value)
            if (found) setSelected(found)
          }}
        >
          {RESOURCES.map(([label]) => <option key={label}>{label}</option>)}
        </select>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={`Search ${(selected?.[0] || 'records').toLowerCase()}`}
        />
        <span className="record-count">{result?.total || items.length || 0} live record{(result?.total || items.length) === 1 ? '' : 's'}</span>
      </div>
      {loading ? (
        <div className="empty-state">Loading live database records…</div>
      ) : error ? (
        <p className="admin-error">{error}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {fields.map((field) => (
                  <th key={field}>{field.replaceAll('_', ' ')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.length ? (
                items.map((row, index) => (
                  <tr key={row?.id || index}>
                    {fields.map((field) => (
                      <td key={field}>{cell(row?.[field])}</td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={Math.max(fields.length, 1)} className="empty-cell">
                    No live records found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
