import { useState } from 'react'
import { formatDate } from '../utils'
import Badge from '../components/Badge'
import PolicyModal from '../components/PolicyModal'
import PolicyDetail from '../components/PolicyDetail'
import { api } from '../api'

export default function Policies({ data, onRefresh }) {
  const { policies, backups, restores } = data
  const [expanded,      setExpanded]      = useState({})
  const [modalPolicy,   setModalPolicy]   = useState(undefined) // undefined=closed, null=create, obj=edit
  const [deleting,      setDeleting]      = useState(null)
  const [toggling,      setToggling]      = useState(null)
  const [detailPolicy,  setDetailPolicy]  = useState(null)

  async function handleDelete(p) {
    if (!window.confirm(`Delete policy "${p.name}"? This cannot be undone.`)) return
    setDeleting(p.id)
    try {
      await api.deletePolicy(p.id)
      onRefresh()
    } catch (err) {
      alert(`Delete failed: ${err.message}`)
    } finally {
      setDeleting(null)
    }
  }

  async function handleToggle(p) {
    setToggling(p.id)
    try {
      await api.updatePolicy(p.id, { is_active: !p.is_active })
      onRefresh()
    } catch (err) {
      alert(`Failed: ${err.message}`)
    } finally {
      setToggling(null)
    }
  }

  return (
    <div className="p-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5">
        <span className="text-sm text-slate-500">{policies.length} protection group{policies.length !== 1 ? 's' : ''}</span>
        <button
          onClick={() => setModalPolicy(null)}
          className="flex items-center gap-2 px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg text-sm font-medium transition-colors"
        >
          + New Policy
        </button>
      </div>

      {policies.length === 0 && (
        <div className="text-center py-16 text-slate-300">
          <div className="text-4xl mb-3">⊕</div>
          <p className="text-sm">No protection groups found.</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {policies.map(p => {
          const pJobs      = backups.filter(b => b.policy_id === p.id)
          const pBackupIds = new Set(pJobs.map(b => b.id))
          const pRestores  = restores.filter(r => pBackupIds.has(r.backup_job_id))
          const success    = pJobs.filter(b => b.status === 'success').length
          const failed     = pJobs.filter(b => b.status === 'failed').length
          const running    = pJobs.filter(b => ['running','queued'].includes(b.status)).length
          const totalSize  = pJobs.reduce((a, b) => a + (parseFloat(b.size_gb) || 0), 0).toFixed(2)
          const successRate = pJobs.length ? Math.round(success / pJobs.length * 100) : null
          const showRestores = expanded[p.id]

          return (
            <div key={p.id} className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
              {/* Header */}
              <div className="px-5 py-4 border-b border-slate-50 flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-bold text-slate-800 text-base truncate">{p.name}</div>
                  <div className="text-xs text-slate-400 font-mono mt-0.5 truncate">{p.id}</div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
                    p.is_active
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-slate-50 text-slate-500 border-slate-200'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${p.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                    {p.is_active ? 'Active' : 'Paused'}
                  </span>
                </div>
              </div>

              {/* Schedule info */}
              <div className="px-5 py-4 space-y-2.5">
                <div className="flex items-center gap-2.5 text-sm">
                  <span className="text-lg">📅</span>
                  <div>
                    <div className="font-medium text-slate-700">{p.schedule_description ?? p.schedule}</div>
                    <code className="text-xs text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded font-mono">{p.schedule}</code>
                  </div>
                </div>

                {p.is_active && p.next_run && (
                  <div className="flex items-center gap-2.5 text-sm">
                    <span className="text-lg">🕐</span>
                    <div>
                      <div className="text-xs text-slate-400">Next run</div>
                      <div className="font-medium text-slate-700 text-sm">{p.next_run}</div>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-2.5 text-sm">
                  <span className="text-lg">🗑</span>
                  <div className="text-slate-600">Retention: <strong>{p.retention_days} days</strong></div>
                </div>

                <div className="flex items-center gap-2.5 text-sm">
                  <span className="text-lg">🖥</span>
                  <div className="text-slate-600"><strong>{(p.vm_ids ?? []).length}</strong> VM{(p.vm_ids ?? []).length !== 1 ? 's' : ''} protected</div>
                </div>

                <div className="flex items-center gap-2.5 text-sm">
                  <span className="text-lg">△</span>
                  {p.incremental_enabled
                    ? <div className="text-slate-600">
                        Incremental — full every <strong>{p.full_backup_interval}</strong> backups
                      </div>
                    : <div className="text-slate-400">Full backups only</div>
                  }
                </div>
              </div>

              {/* Stats bar */}
              <div className="border-t border-slate-50 px-5 py-3 bg-slate-50/50">
                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <span className="text-emerald-600 font-semibold">✓ {success}</span>
                  <span className="text-red-500 font-semibold">✕ {failed}</span>
                  {running > 0 && <span className="text-blue-500 font-semibold">⟳ {running}</span>}
                  <span className="ml-auto text-slate-400">{totalSize} GB stored</span>
                  {successRate !== null && (
                    <span className={`font-semibold ${successRate === 100 ? 'text-emerald-600' : successRate >= 70 ? 'text-amber-500' : 'text-red-500'}`}>
                      {successRate}% ok
                    </span>
                  )}
                </div>
                {pJobs.length > 0 && (
                  <div className="mt-2 h-1 bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${successRate ?? 0}%` }} />
                  </div>
                )}
              </div>

              {/* Restore jobs section */}
              <div className="border-t border-slate-100">
                <button
                  onClick={() => setExpanded(e => ({ ...e, [p.id]: !e[p.id] }))}
                  className="w-full flex items-center justify-between px-5 py-2.5 text-xs font-medium text-slate-500 hover:bg-slate-50 transition-colors"
                >
                  <span>Restore Jobs ({pRestores.length})</span>
                  <span className="text-slate-300">{showRestores ? '▲' : '▼'}</span>
                </button>

                {showRestores && (
                  <div className="px-5 pb-4 space-y-2">
                    {pRestores.length === 0 ? (
                      <p className="text-xs text-slate-300 py-2 text-center">No restore jobs for this policy.</p>
                    ) : (
                      pRestores.map(r => (
                        <div key={r.id} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2 text-xs">
                          <div className="min-w-0 flex-1">
                            <div className="font-medium text-slate-700 truncate">{r.target_vm_name}</div>
                            <div className="text-slate-400 font-mono truncate">{r.id.substring(0, 12)}…</div>
                          </div>
                          <div className="ml-3 flex-shrink-0">
                            <Badge status={r.status} />
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="border-t border-slate-100 px-5 py-3 space-y-2">
                <button
                  onClick={() => setDetailPolicy(p)}
                  className="w-full py-1.5 rounded-lg text-xs font-medium bg-sky-50 border border-sky-200 text-sky-700 hover:bg-sky-100 transition-colors"
                >
                  View Details
                </button>
                <div className="flex items-center gap-2">
                <button
                  onClick={() => setModalPolicy(p)}
                  className="flex-1 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleToggle(p)}
                  disabled={toggling === p.id}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50 ${
                    p.is_active
                      ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
                      : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                  }`}
                >
                  {toggling === p.id ? '…' : p.is_active ? 'Pause' : 'Resume'}
                </button>
                <button
                  onClick={() => handleDelete(p)}
                  disabled={deleting === p.id}
                  className="flex-1 py-1.5 rounded-lg text-xs font-medium border border-red-200 text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                >
                  {deleting === p.id ? '…' : 'Delete'}
                </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {modalPolicy !== undefined && (
        <PolicyModal
          policy={modalPolicy}
          onClose={() => setModalPolicy(undefined)}
          onSaved={() => { setModalPolicy(undefined); onRefresh() }}
        />
      )}

      {detailPolicy && (
        <PolicyDetail
          policy={detailPolicy}
          backups={backups}
          restores={restores}
          onClose={() => setDetailPolicy(null)}
          onRefresh={onRefresh}
        />
      )}
    </div>
  )
}
