import { useState, useMemo } from 'react'
import Badge from '../components/Badge'
import ErrorModal from '../components/ErrorModal'
import RestoreModal from '../components/RestoreModal'
import FileBrowserModal from '../components/FileBrowserModal'
import { formatDate, formatSize } from '../utils'
import { api } from '../api'

const STATUSES = ['all', 'running', 'queued', 'success', 'failed']

const RECOVERY_BADGE = {
  executing: { label: 'Executing',  cls: 'bg-blue-50  text-blue-600  border-blue-200'   },
  available: { label: 'Available',  cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  expired:   { label: 'Expired',    cls: 'bg-slate-100 text-slate-400 border-slate-200'  },
  failed:    { label: 'Failed',     cls: 'bg-red-50   text-red-500   border-red-200'     },
}

function RecoveryBadge({ status }) {
  const b = RECOVERY_BADGE[status] ?? RECOVERY_BADGE.available
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${b.cls}`}>
      {b.label}
    </span>
  )
}

export default function BackupJobs({ data, onRefresh }) {
  const [filter,      setFilter]      = useState('all')
  const [search,      setSearch]      = useState('')
  const [errorJob,    setErrorJob]    = useState(null)
  const [restoreJob,  setRestoreJob]  = useState(null)
  const [flrJob,      setFlrJob]      = useState(null)
  const [selected,    setSelected]    = useState(new Set())
  const [deleting,    setDeleting]    = useState(false)

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

  const allSelected  = filtered.length > 0 && filtered.every(j => selected.has(j.id))
  const someSelected = selected.size > 0

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(filtered.map(j => j.id)))
    }
  }

  function toggleOne(id) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function handleBulkDelete() {
    const ids = [...selected]
    if (!window.confirm(`Delete ${ids.length} recovery point${ids.length > 1 ? 's' : ''}? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await api.bulkDeleteBackups(ids)
      setSelected(new Set())
      onRefresh()
    } catch (err) {
      alert(`Delete failed: ${err.message}`)
    } finally {
      setDeleting(false)
    }
  }

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

      {/* Bulk action bar */}
      {someSelected && (
        <div className="mb-4 flex items-center gap-3 bg-sky-50 border border-sky-200 rounded-xl px-4 py-2.5">
          <span className="text-sm font-medium text-sky-700">
            {selected.size} recovery point{selected.size > 1 ? 's' : ''} selected
          </span>
          <button
            onClick={() => setSelected(new Set())}
            className="text-xs text-sky-500 hover:text-sky-700 underline"
          >
            Clear
          </button>
          <button
            onClick={handleBulkDelete}
            disabled={deleting}
            className="ml-auto flex items-center gap-2 px-3.5 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {deleting ? 'Deleting…' : `🗑 Delete ${selected.size} selected`}
          </button>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">Recovery Points</span>
          <span className="text-xs text-slate-400">{filtered.length} records</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-50">
                <th className="px-4 py-2.5 w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="accent-sky-500 cursor-pointer"
                  />
                </th>
                {['VM', 'Policy', 'Type', 'Job Status', 'Recovery', 'Expires', 'Size', 'Started', 'Error', ''].map(h => (
                  <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 py-2.5 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.length === 0 && (
                <tr><td colSpan={11} className="text-center py-12 text-slate-300">No jobs match the filter.</td></tr>
              )}
              {filtered.map(j => (
                <tr
                  key={j.id}
                  className={`hover:bg-slate-50/60 transition-colors ${selected.has(j.id) ? 'bg-sky-50/40' : ''}`}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(j.id)}
                      onChange={() => toggleOne(j.id)}
                      className="accent-sky-500 cursor-pointer"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{j.vm_name ?? '—'}</div>
                    <div className="text-xs text-slate-400 font-mono">{j.vm_id?.substring(0, 8)}…</div>
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{policyMap[j.policy_id] ?? '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-0.5">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold w-fit ${
                        j.backup_type === 'incremental'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : 'bg-sky-50 text-sky-700 border border-sky-200'
                      }`}>
                        {j.backup_type === 'incremental' ? '△ Inc' : '● Full'}
                      </span>
                      {j.cinder_backup_id && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold w-fit bg-teal-50 text-teal-700 border border-teal-200">
                          ⚡ CBT
                        </span>
                      )}
                      {j.backup_type === 'incremental' && j.parent_backup_id && !j.cinder_backup_id && (
                        <span className="text-[10px] text-slate-400 font-mono" title={`Base: ${j.parent_backup_id}`}>
                          base {j.parent_backup_id.substring(0, 8)}…
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge status={j.status} />
                    {(j.status === 'running' || j.status === 'queued') && (
                      <div className="mt-1.5 w-28">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[10px] text-slate-400 truncate max-w-[80px]">{j.progress_msg || 'Queued…'}</span>
                          <span className="text-[10px] font-semibold text-sky-600 ml-1">{j.progress || 0}%</span>
                        </div>
                        <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-sky-400 to-indigo-500 rounded-full transition-all duration-500"
                            style={{ width: `${j.progress || 0}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <RecoveryBadge status={j.recovery_status ?? j.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                    {j.expires_at
                      ? <span className={j.recovery_status === 'expired' ? 'text-red-400' : ''}>
                          {formatDate(j.expires_at)}
                        </span>
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{formatSize(j.size_gb)}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(j.started_at)}</td>
                  <td className="px-4 py-3">
                    {j.error_msg
                      ? <button onClick={() => setErrorJob(j)} className="flex items-center gap-1 text-red-500 hover:text-red-700 text-xs text-left">
                          <span className="text-base leading-none">⚠</span>
                          <span className="underline decoration-dotted max-w-[140px] truncate">{j.error_msg}</span>
                        </button>
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {j.status === 'success' && j.recovery_status !== 'expired' && (
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => setRestoreJob(j)}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-50 hover:bg-violet-100 border border-violet-200 text-violet-700 text-xs font-medium transition-colors whitespace-nowrap"
                        >
                          ↩ Restore
                        </button>
                        <button
                          onClick={() => setFlrJob(j)}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-teal-50 hover:bg-teal-100 border border-teal-200 text-teal-700 text-xs font-medium transition-colors whitespace-nowrap"
                          title="File-Level Restore"
                        >
                          📄 Files
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ErrorModal       job={errorJob}   onClose={() => setErrorJob(null)} />
      <RestoreModal     backup={restoreJob} onClose={() => setRestoreJob(null)} onSuccess={onRefresh} />
      {flrJob && <FileBrowserModal backup={flrJob} onClose={() => setFlrJob(null)} />}
    </div>
  )
}
