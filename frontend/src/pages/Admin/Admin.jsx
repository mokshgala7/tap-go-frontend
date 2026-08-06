import { useEffect, useState } from 'react'
import { useNavigate } from '../../routes/navigation.jsx'
import { adminRequest, API_BASE, fileUrl } from './api.js'
import DatabaseViewer from './database/DatabaseViewer.jsx'
import DemoInfoCard from '../../components/Common/DemoInfoCard.jsx'
import './admin.css'

const navigation = [
  ['dashboard', 'Overview', '▦'], ['drivers', 'Driver Management', '♙'], ['passengers', 'Passenger Management', '♟'],
  ['documents', 'Driver Documents', '▤'], ['requests', 'Edit Requests', '✓'], ['transactions', 'Transactions', '⇄'],
  ['wallets', 'Wallets', '◉'], ['fraud', 'Fraud Centre', '⚑'], ['logs', 'Activity Logs', '◷'],
  ['settings', 'Settings', '⚙'], ['database', 'Database Viewer', '▤'],
]
const resourceConfig = {
  documents: ['Driver Documents', '/documents'], requests: ['Edit Requests', '/edit-requests'], transactions: ['Transactions', '/transactions'],
  wallets: ['Wallet Management', '/wallets'], fraud: ['Fraud Management', '/fraud-alerts'], logs: ['Activity Logs', '/activity-logs'],
}

const number = (value) => new Intl.NumberFormat('en-IN').format(value || 0)
const money = (value) => `₹${new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0)}`
const date = (value) => value ? new Date(value).toLocaleString() : '—'

function LoadState({ error, children }) { return error ? <p className="admin-error">{error}</p> : children }
function Badge({ value }) { return <span className={`status status-${String(value || 'unknown').toLowerCase()}`}>{value || 'unknown'}</span> }
function Empty({ text = 'No live records yet.' }) { return <div className="empty-state">{text}</div> }

function AdminLogin({ onLogin }) {
  const [email, setEmail] = useState('admin@example.com')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const submit = async (event) => {
    event.preventDefault(); setError(''); setWorking(true)
    try { onLogin(await adminRequest('/login', null, { method: 'POST', body: JSON.stringify({ email, password }) })) }
    catch (loginError) { setError(loginError.message) }
    finally { setWorking(false) }
  }
  return <main className="admin-login"><section className="admin-login-card"><div className="admin-mark">T&G</div><span className="eyebrow">Tap&Go control centre</span><h1>Administrator sign in</h1><p>Use the administrator account configured in the backend environment.</p><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>{error && <p className="admin-error">{error}</p>}<button className="primary-button" disabled={working}>{working ? 'Signing in…' : 'Sign in securely'}</button></form><small>Default development credentials are set in the backend environment.</small></section></main>
}

function Dashboard({ adminId }) {
  const [stats, setStats] = useState(null); const [error, setError] = useState('')
  useEffect(() => { adminRequest('/dashboard', adminId).then(setStats).catch((err) => setError(err.message)) }, [adminId])
  const cards = stats && [
    ['Total Drivers', stats.total_drivers, 'Driver accounts'], ['Active Drivers', stats.active_drivers, `${stats.pending_drivers} pending approval`], ['Suspended Drivers', stats.suspended_drivers, 'Restricted accounts'],
    ['Total Passengers', stats.total_passengers, `${stats.active_passengers} active`], ['Transactions', stats.total_transactions, `${stats.today_transactions} today`], ['Wallet Balance', money(stats.wallet_balance), 'Across live wallets'],
    ['Revenue', money(stats.revenue), 'Completed transactions'], ['Fraud Alerts', stats.fraud_alerts, 'Awaiting review'], ['Edit Requests', stats.pending_edit_requests, 'Awaiting action'],
  ]
  return <section className="admin-section"><DemoInfoCard type="admin_dashboard" className="mb-6" /><div className="section-heading"><div><span className="eyebrow">Operations at a glance</span><h2>Dashboard Overview</h2><p>Live counts from the Tap&Go backend database.</p></div></div><LoadState error={error}>{!stats ? <Empty text="Loading live operations…" /> : <div className="metric-grid">{cards.map(([label, value, hint]) => <article className="metric-card" key={label}><div className="metric-icon">◈</div><p>{label}</p><strong>{typeof value === 'number' ? number(value) : value}</strong><small>{hint}</small></article>)}</div>}</LoadState></section>
}

function UserDirectory({ adminId, type }) {
  const [result, setResult] = useState({ items: [] }); const [search, setSearch] = useState(''); const [status, setStatus] = useState(''); const [error, setError] = useState(''); const [detail, setDetail] = useState(null)
  const load = () => adminRequest(`/users?account_type=${type}&search=${encodeURIComponent(search)}${status ? `&status=${status}` : ''}`, adminId).then(setResult).catch((err) => setError(err.message))
  useEffect(() => { load() }, [adminId, type, status, search])
  const action = async (userId, actionName) => { if (actionName === 'delete' && !window.confirm('Delete this account and its wallet record?')) return; try { await adminRequest(`/users/${userId}/action`, adminId, { method: 'POST', body: JSON.stringify({ action: actionName }) }); load(); if (detail?.id === userId) setDetail(null) } catch (err) { setError(err.message) } }
  const open = async (id) => { try { setDetail(await adminRequest(`/users/${id}`, adminId)) } catch (err) { setError(err.message) } }
  const plural = type === 'driver' ? 'Drivers' : 'Passengers'
  return <section className="admin-section"><div className="section-heading"><div><span className="eyebrow">Live account directory</span><h2>{plural}</h2><p>Search, inspect, approve, suspend, edit, or remove live accounts.</p></div></div><div className="table-controls"><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && load()} placeholder={`Search ${plural.toLowerCase()} by name, email or phone`} /><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All states</option><option value="active">Active</option><option value="pending">Pending</option><option value="suspended">Suspended</option><option value="rejected">Rejected</option></select><button className="secondary-button" onClick={load}>Search</button></div><LoadState error={error}><div className="table-wrap"><table><thead><tr><th>Person</th><th>Phone</th><th>City</th><th>Wallet</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody>{result.items?.length ? result.items.map((user) => <tr key={user.id}><td><button className="table-link" onClick={() => open(user.id)}>{user.name}<small>{user.email}</small></button></td><td>{user.phone}</td><td>{user.city || '—'}</td><td>{money(user.wallet_balance)}</td><td><Badge value={user.status} /></td><td>{date(user.created_at)}</td><td className="actions"><button onClick={() => action(user.id, user.status === 'suspended' ? 'activate' : 'suspend')}>{user.status === 'suspended' ? 'Activate' : 'Suspend'}</button>{type === 'driver' && user.status === 'pending' && <button onClick={() => action(user.id, 'approve')}>Approve</button>}<button onClick={() => action(user.id, 'delete')}>Delete</button></td></tr>) : <tr><td colSpan="7"><Empty /></td></tr>}</tbody></table></div></LoadState>{detail && <UserModal data={detail} adminId={adminId} onClose={() => setDetail(null)} onAction={action} onSaved={() => { load(); open(detail.id) }} />}</section>
}

function UserModal({ data, adminId, onClose, onAction, onSaved }) {
  const [editing, setEditing] = useState(false); const [draft, setDraft] = useState({ name: data.name || '', email: data.email || '', city: data.city || '', address: data.address || '' }); const [error, setError] = useState('')
  const save = async () => { try { await adminRequest(`/users/${data.id}`, adminId, { method: 'PUT', body: JSON.stringify(draft) }); setEditing(false); onSaved() } catch (err) { setError(err.message) } }
  return <div className="modal-backdrop" role="presentation"><article className="profile-modal" role="dialog" aria-modal="true"><button className="modal-close" onClick={onClose}>×</button><span className="eyebrow">{data.account_type} profile</span><h2>{data.name}</h2>{error && <p className="admin-error">{error}</p>}<div className="profile-grid">{editing ? <><label>Name<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label>Email<input value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label><label>City<input value={draft.city} onChange={(event) => setDraft({ ...draft, city: event.target.value })} /></label><label>Address<input value={draft.address} onChange={(event) => setDraft({ ...draft, address: event.target.value })} /></label></> : <><p><b>Email</b>{data.email}</p><p><b>Phone</b>{data.phone}</p><p><b>Wallet balance</b>{money(data.wallet_balance)}</p><p><b>Wallet status</b>{data.wallet_frozen ? 'Frozen' : 'Available'}</p><p><b>QR identifier</b>{data.qr_identifier || 'Not issued'}</p><p><b>NFC identifier</b>{data.nfc_identifier || 'Not issued'}</p></>}</div><h3>Uploaded documents</h3>{data.documents?.length ? <ul className="document-list">{data.documents.map((document) => <li key={document.id}><span>{document.type}</span><a href={fileUrl(document.file_path)} target="_blank" rel="noreferrer">Open</a></li>)}</ul> : <Empty text="No uploaded documents." />}<h3>Recent transactions</h3>{data.transactions?.length ? <div className="modal-transactions">{data.transactions.map((transaction) => <p key={transaction.id}>{transaction.reference} <b>{money(transaction.amount)}</b> <Badge value={transaction.status} /></p>)}</div> : <Empty text="No transactions recorded." />}<div className="modal-actions">{editing ? <button className="primary-button" onClick={save}>Save changes</button> : <button className="secondary-button" onClick={() => setEditing(true)}>Edit profile</button>}<button className="secondary-button" onClick={() => onAction(data.id, data.status === 'suspended' ? 'activate' : 'suspend')}>{data.status === 'suspended' ? 'Activate account' : 'Suspend account'}</button></div></article></div>
}

function SimpleResource({ adminId, kind }) {
  const config = resourceConfig[kind] || ['Operational Records', '/activity-logs']
  const [result, setResult] = useState({ items: [] }); const [error, setError] = useState(''); const [search, setSearch] = useState(''); const [loading, setLoading] = useState(true)
  const load = () => {
    setLoading(true)
    adminRequest(`${config[1]}${search && ['documents', 'transactions', 'wallets'].includes(kind) ? `?search=${encodeURIComponent(search)}` : ''}`, adminId)
      .then((data) => {
        setResult(data && typeof data === 'object' ? data : { items: [] })
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }
  useEffect(() => { load() }, [adminId, kind, search])
  const act = async (id, path, body) => { try { await adminRequest(path, adminId, { method: 'POST', body: JSON.stringify(body) }); load() } catch (err) { setError(err.message) } }
  const exportCsv = async () => { try { const response = await fetch(`${API_BASE}/api/admin/transactions/export`, { headers: { 'X-Admin-Id': String(adminId) } }); if (!response.ok) throw new Error('Could not export transactions.'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'tapgo-transactions.csv'; link.click(); URL.revokeObjectURL(url) } catch (err) { setError(err.message) } }
  const rows = result.items || []; const columns = Object.keys(rows[0] || {}).filter((column) => !['proof_path', 'file_path', 'user_id', 'transaction_id'].includes(column))
  return <section className="admin-section"><div className="section-heading"><div><span className="eyebrow">Live operational records</span><h2>{config[0]}</h2><p>{kind === 'documents' ? 'All uploaded files, generated dynamically from database fields.' : kind === 'fraud' ? 'Risk alerts ready for AI-generated signals.' : 'Search and act on records stored in MySQL.'}</p></div>{kind === 'transactions' && <button className="primary-button" onClick={exportCsv}>Export CSV</button>}</div>{['documents', 'transactions', 'wallets'].includes(kind) && <div className="table-controls"><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && load()} placeholder="Search live records" /><button className="secondary-button" onClick={load}>Search</button></div>}<LoadState error={error}>{loading ? <Empty text="Loading live records…" /> : <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}<th>Actions</th></tr></thead><tbody>{rows.length ? rows.map((row, index) => <tr key={row.id || index}>{columns.map((column) => <td key={column}>{typeof row[column] === 'boolean' ? (row[column] ? 'Yes' : 'No') : column.includes('amount') || column === 'balance' ? money(row[column]) : column.includes('at') ? date(row[column]) : row[column] || '—'}</td>)}<td className="actions">{kind === 'documents' && row.file_path && <a href={fileUrl(row.file_path)} target="_blank" rel="noreferrer">Open</a>}{kind === 'requests' && row.status === 'pending' && <><button onClick={() => act(row.id, `/edit-requests/${row.id}/review`, { action: 'approve' })}>Approve</button><button onClick={() => act(row.id, `/edit-requests/${row.id}/review`, { action: 'reject' })}>Reject</button></>}{kind === 'wallets' && <button onClick={() => act(row.id, `/wallets/${row.id}`, { frozen: !row.is_frozen })}>{row.is_frozen ? 'Unfreeze' : 'Freeze'}</button>}{kind === 'fraud' && row.status === 'open' && <><button onClick={() => act(row.id, `/fraud-alerts/${row.id}/review`, { action: 'safe' })}>Mark safe</button><button onClick={() => act(row.id, `/fraud-alerts/${row.id}/review`, { action: 'block' })}>Block</button><button onClick={() => act(row.id, `/fraud-alerts/${row.id}/review`, { action: 'freeze' })}>Freeze</button></>}</td></tr>) : <tr><td colSpan={Math.max(columns.length + 1, 1)}><Empty /></td></tr>}</tbody></table></div>}</LoadState></section>
}

function Settings({ adminId }) {
  const [items, setItems] = useState([])
  const [projectName, setProjectName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    adminRequest('/settings', adminId)
      .then((data) => {
        setItems(data?.items || [])
        setProjectName((data?.items || []).find((item) => item.key === 'project_name')?.value || '')
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }

  useEffect(() => { load() }, [adminId])

  const save = async () => {
    try {
      await adminRequest('/settings/project_name', adminId, { method: 'PUT', body: JSON.stringify({ value: projectName }) })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="admin-section narrow-section">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Configuration</span>
          <h2>Settings</h2>
          <p>Project configuration is stored in MySQL and ready for future controls.</p>
        </div>
      </div>
      <LoadState error={error}>
        {loading ? (
          <Empty text="Loading settings…" />
        ) : (
          <div>
            <label>
              Project name
              <input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Tap&Go" />
            </label>
            <button className="primary-button" onClick={save}>Save project name</button>
            <h3>Saved settings</h3>
            {items.length ? (
              <ul className="settings-list">
                {items.map((item) => (
                  <li key={item.key}>
                    <b>{item.key}</b>
                    <span>{item.value || '—'}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty text="No additional settings saved." />
            )}
          </div>
        )}
      </LoadState>
    </section>
  )
}

function AdminShell({ admin, onLogout }) {
  const [page, setPageState] = useState(() => sessionStorage.getItem('admin_page') || 'dashboard')
  const setPage = (newPage) => {
    setPageState(newPage)
    try { sessionStorage.setItem('admin_page', newPage) } catch {}
  }
  const render = () => {
    const props = { adminId: admin.id }
    if (page === 'dashboard') return <Dashboard {...props} />
    if (page === 'drivers' || page === 'passengers') return <UserDirectory {...props} type={page === 'drivers' ? 'driver' : 'passenger'} />
    if (page === 'database') return <DatabaseViewer {...props} />
    if (page === 'settings') return <Settings {...props} />
    return <SimpleResource {...props} kind={page} />
  }
  return <div className="admin-shell"><aside className="admin-sidebar"><div className="admin-brand"><span>T&G</span><div><b>Tap & Go</b><small>ADMIN CONSOLE</small></div></div><nav>{navigation.map(([id, label, icon]) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}><i>{icon}</i>{label}</button>)}</nav><button className="logout-button" onClick={onLogout}>⇥ Sign out</button></aside><main className="admin-content"><header className="admin-topbar"><div><span className="eyebrow">Signed in as</span><strong>{admin.name}</strong></div><span className="admin-avatar">{admin.name.charAt(0)}</span></header>{render()}</main></div>
}

function Admin() {
  const navigate = useNavigate()
  const [admin, setAdminState] = useState(() => {
    try {
      const raw = sessionStorage.getItem('tapgo_admin_session')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })

  const setAdmin = (adminData) => {
    setAdminState(adminData)
    try {
      if (adminData) sessionStorage.setItem('tapgo_admin_session', JSON.stringify(adminData))
      else sessionStorage.removeItem('tapgo_admin_session')
    } catch {}
  }

  if (!admin) return <AdminLogin onLogin={(result) => setAdmin(result.admin)} />
  return <AdminShell admin={admin} onLogout={() => { setAdmin(null); try { sessionStorage.clear() } catch {} navigate('/') }} />
}

export default Admin
