import { useState, useMemo } from 'react'
import Badge from '../components/Badge'
import ErrorModal from '../components/ErrorModal'
import RestoreModal from '../components/RestoreModal'
import { formatDate, formatSize } from '../utils'

const STATUSES = ['all', 'running', 'queued', 'success', 'failed']

export default function BackupJobs({ data, onRefresh }) {
  const [filter,      setFilter]      = useState('all')
  const [search,      setSearch]      = useState('')
  const [errorJob,    setErrorJob]    = useState(null)
  const [restoreJob,  setRestoreJob]  = useState(null)

  const { backups, policies } = data
  const policyMap = Object.fromEntries(policies.map(p => [p.id, p.name]))

  const filtered = useMemo(() => backups.filter(j => {
    if (filter !== 'all' && j.status !== filter) return false
    if (search) {
      const q = search.toLowerCase()
      return (j.vm_name ?? '').toLowerCase().includes(q) ||
             (j.vm_id ?? '').toLowerCase().includes(q) ||
             (policyMap[j.policy_id] ?? '').toLowerCase().includes(q)
    }
    return true
  }), [backups, filter, search, policyMap])

  const counts = useMemo(() =>
    STATUSES.slice(1).reduce((acc, s) => ({ ...acc, [s]: backups.filter(j => j.status === s).length }), {}),
  [backups])

  return (
    <div className="p-6">
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search VM name or policy…"
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-200"
        />
        <div className="flex gap-1 bg-white border border-slate-200 rounded-lg p-1">
          {STATUSES.map(s => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                filter === s ? 'bg-sky-500 text-white' : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {s === 'all' ? `All (${backups.length})` : `${s} (${counts[s] ?? 0})`}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">Backup Jobs</span>
          <span className="text-xs text-slate-400">{filtered.length} records</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-50">
                {['VM', 'Policy', 'Status', 'Size', 'Backup Path', 'Started', 'Completed', 'Error', ''].map(h => (
                  <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-5 py-2.5 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.length === 0 && (
                <tr><td colSpan={9} className="text-center py-12 text-slate-300">No jobs match the filter.</td></tr>
              )}
              {filtered.map(j => (
                <tr key={j.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-5 py-3">
                    <div className="font-medium text-slate-800">{j.vm_name ?? '—'}</div>
                    <div className="text-xs text-slate-400 font-mono">{j.vm_id?.substring(0, 8)}…</div>
                  </td>
                  <td className="px-5 py-3 text-slate-500 text-xs">{policyMap[j.policy_id] ?? '—'}</td>
                  <td className="px-5 py-3"><Badge status={j.status} /></td>
                  <td className="px-5 py-3 text-slate-600 whitespace-nowrap">{formatSize(j.size_gb)}</td>
                  <td className="px-5 py-3">
                    {j.backup_path
                      ? <span className="font-mono text-xs text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded max-w-[180px] truncate block" title={j.backup_path}>
                          {j.backup_path.replace('s3://vaultstack-backups/', '').substring(0, 32)}…
                        </span>
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(j.started_at)}</td>
                  <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(j.completed_at)}</td>
                  <td className="px-5 py-3">
                    {j.error_msg
                      ? <button onClick={() => setErrorJob(j)} className="flex items-center gap-1 text-red-500 hover:text-red-700 text-xs text-left">
                          <span className="text-base leading-none">⚠</span>
                          <span className="underline decoration-dotted max-w-[140px] truncate">{j.error_msg}</span>
                        </button>
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-5 py-3">
                    {j.status === 'success' && (
                      <button
                        onClick={() => setRestoreJob(j)}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-50 hover:bg-violet-100 border border-violet-200 text-violet-700 text-xs font-medium transition-colors whitespace-nowrap"
                      >
                        ↩ Restore
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ErrorModal   job={errorJob}   onClose={() => setErrorJob(null)} />
      <RestoreModal backup={restoreJob} onClose={() => setRestoreJob(null)} onSuccess={onRefresh} />
    </div>
  )
}
