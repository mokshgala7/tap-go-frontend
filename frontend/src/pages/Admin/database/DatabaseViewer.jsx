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
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    const params = search.trim() && ['Drivers', 'Passengers', 'Transactions', 'Wallets', 'Documents'].includes(selected[0]) ? `&search=${encodeURIComponent(search.trim())}` : ''
    adminRequest(`${selected[1]}${selected[1].includes('?') ? params : `?${params.replace(/^&/, '')}`}`, adminId)
      .then((data) => alive && setResult(data))
      .catch((requestError) => alive && setError(requestError.message))
    return () => { alive = false }
  }, [adminId, selected, search])

  const fields = Object.keys(result.items?.[0] || {}).filter((key) => !['proof_path', 'file_path'].includes(key))
  return (
    <section className="admin-section">
      <div className="section-heading">
        <div><span className="eyebrow">Internal developer tool</span><h2>Database Viewer</h2><p>Read-only, paginated access to the live MySQL records through FastAPI.</p></div>
      </div>
      <div className="database-toolbar">
        <select value={selected[0]} onChange={(event) => setSelected(RESOURCES.find(([label]) => label === event.target.value))}>
          {RESOURCES.map(([label]) => <option key={label}>{label}</option>)}
        </select>
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${selected[0].toLowerCase()}`} />
        <span className="record-count">{result.total || 0} live record{result.total === 1 ? '' : 's'}</span>
      </div>
      {error ? <p className="admin-error">{error}</p> : <div className="table-wrap"><table><thead><tr>{fields.map((field) => <th key={field}>{field.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{result.items?.length ? result.items.map((row, index) => <tr key={row.id || index}>{fields.map((field) => <td key={field}>{cell(row[field])}</td>)}</tr>) : <tr><td colSpan={Math.max(fields.length, 1)} className="empty-cell">No live records yet.</td></tr>}</tbody></table></div>}
    </section>
  )
}
