import { useState, useEffect } from 'react'
import { api } from '../api'

const ACTION_COLOR = {
  delete_backup:  'bg-red-50 text-red-700 border-red-200',
  lock_backup:    'bg-orange-50 text-orange-700 border-orange-200',
  unlock_backup:  'bg-slate-50 text-slate-600 border-slate-200',
  create_backup:  'bg-sky-50 text-sky-700 border-sky-200',
  restore:        'bg-violet-50 text-violet-700 border-violet-200',
}

function ActionBadge({ action }) {
  const cls = ACTION_COLOR[action] ?? 'bg-slate-50 text-slate-600 border-slate-200'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>
      {action}
    </span>
  )
}

export default function AuditLog() {
  const [logs,    setLogs]    = useState([])
  const [loading, setLoading] = useState(true)
  const [search,  setSearch]  = useState('')
  const [entity,  setEntity]  = useState('')

  async function load() {
    setLoading(true)
    try {
      const params = {}
      if (search) params.action = search
      if (entity) params.entity_type = entity
      const data = await api.auditLogs(Object.keys(params).length ? params : null)
      setLogs(data ?? [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-6">
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && load()}
          placeholder="Search by action…"
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-sky-200"
        />
        <select
          value={entity}
          onChange={e => setEntity(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200"
        >
          <option value="">All entities</option>
          <option value="backup">backup</option>
          <option value="policy">policy</option>
          <option value="restore">restore</option>
        </select>
        <button
          onClick={load}
          className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-white rounded-lg text-sm font-medium transition-colors"
        >
          Apply
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">Audit Log</span>
          <span className="text-xs text-slate-400">{logs.length} events</span>
        </div>
        {loading ? (
          <div className="py-16 text-center text-slate-400">Loading…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-50">
                  {['Time', 'Action', 'Entity', 'Entity ID', 'Details'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 py-2.5 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {logs.length === 0 && (
                  <tr><td colSpan={5} className="text-center py-12 text-slate-300">No audit events found.</td></tr>
                )}
                {logs.map(l => (
                  <tr key={l.id} className="hover:bg-slate-50/60">
                    <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                      {new Date(l.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <ActionBadge action={l.action} />
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{l.entity_type ?? '—'}</td>
                    <td className="px-4 py-3 text-xs text-slate-400 font-mono">
                      {l.entity_id ? `${l.entity_id.substring(0, 12)}…` : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 max-w-xs truncate">{l.details ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
