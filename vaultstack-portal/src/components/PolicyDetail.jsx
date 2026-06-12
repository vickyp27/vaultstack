import { useState } from 'react'
import { api } from '../api'
import RestoreModal from './RestoreModal'
import PolicyModal from './PolicyModal'

export default function PolicyDetail({ policy, backups, restores, onClose, onRefresh }) {
  const pBackups  = (backups  ?? []).filter(b => b.policy_id === policy.id)
  const pBackupIds = new Set(pBackups.map(b => b.id))
  const pRestores  = (restores ?? []).filter(r => pBackupIds.has(r.backup_job_id))

  // Sort backups newest first
  const sortedBackups = [...pBackups].sort((a, b) => {
    const ta = a.started_at ? new Date(a.started_at).getTime() : 0
    const tb = b.started_at ? new Date(b.started_at).getTime() : 0
    return tb - ta
  })

  const [selected,      setSelected]      = useState(new Set())
  const [bulkDeleting,  setBulkDeleting]  = useState(false)
  const [restoreTarget, setRestoreTarget] = useState(null)
  const [deletingId,    setDeletingId]    = useState(null)
  const [triggering,    setTriggering]    = useState(false)
  const [backupResult,  setBackupResult]  = useState(null)
  const [editOpen,      setEditOpen]      = useState(false)
  const [toggling,      setToggling]      = useState(false)
  const [deleting,      setDeleting]      = useState(false)
  const [showRestores,  setShowRestores]  = useState(false)

  // ── Backup Now ─────────────────────────────────────────────────────────────
  async function handleBackupNow() {
    const vmIds = policy.vm_ids ?? []
    if (vmIds.length === 0) {
      setBackupResult({ ok: false, msg: 'No VMs attached to this policy.' })
      return
    }
    setTriggering(true)
    setBackupResult(null)
    try {
      for (const vmId of vmIds) {
        await api.createBackup({ vm_id: vmId, policy_id: policy.id })
      }
      setBackupResult({ ok: true, msg: `Backup queued for ${vmIds.length} VM(s).` })
      onRefresh()
    } catch (err) {
      setBackupResult({ ok: false, msg: err.message })
    } finally {
      setTriggering(false)
    }
  }

  // ── Toggle active ──────────────────────────────────────────────────────────
  async function handleToggle() {
    setToggling(true)
    try {
      await api.updatePolicy(policy.id, { is_active: !policy.is_active })
      onRefresh()
    } catch (err) {
      alert(`Failed: ${err.message}`)
    } finally {
      setToggling(false)
    }
  }

  // ── Delete policy ──────────────────────────────────────────────────────────
  async function handleDeletePolicy() {
    if (!window.confirm(`Delete policy "${policy.name}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await api.deletePolicy(policy.id)
      onRefresh()
      onClose()
    } catch (err) {
      alert(`Delete failed: ${err.message}`)
      setDeleting(false)
    }
  }

  // ── Single backup delete ───────────────────────────────────────────────────
  async function handleDeleteBackup(id) {
    if (!window.confirm('Delete this recovery point?')) return
    setDeletingId(id)
    try {
      await api.deleteBackup(id)
      onRefresh()
    } catch (err) {
      alert(`Delete failed: ${err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  // ── Bulk delete ────────────────────────────────────────────────────────────
  async function handleBulkDelete() {
    if (!window.confirm(`Delete ${selected.size} recovery point(s)?`)) return
    setBulkDeleting(true)
    try {
      await api.bulkDeleteBackups(Array.from(selected))
      setSelected(new Set())
      onRefresh()
    } catch (err) {
      alert(`Bulk delete failed: ${err.message}`)
    } finally {
      setBulkDeleting(false)
    }
  }

  // ── Selection helpers ──────────────────────────────────────────────────────
  function toggleSelect(id) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selected.size === sortedBackups.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(sortedBackups.map(b => b.id)))
    }
  }

  // ── Badges ─────────────────────────────────────────────────────────────────
  function TypeBadge({ job }) {
    if (job.backup_type === 'incremental' || job.is_incremental) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          △ INC
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
        ● FULL
      </span>
    )
  }

  function RecoveryStatusBadge({ status }) {
    const s = (status ?? '').toLowerCase()
    if (s === 'executing') return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
        ⟳ Executing
      </span>
    )
    if (s === 'available' || s === 'success') return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
        ✓ Available
      </span>
    )
    if (s === 'expired') return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">
        ⊘ Expired
      </span>
    )
    if (s === 'failed') return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-600 border border-red-200">
        ✕ Failed
      </span>
    )
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">
        {status ?? '—'}
      </span>
    )
  }

  const vmCount = (policy.vm_ids ?? []).length

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 flex bg-black/40 backdrop-blur-sm"
        onClick={e => { if (e.target === e.currentTarget) onClose() }}
      >
        {/* Panel */}
        <div className="w-full max-w-5xl ml-auto h-full bg-white overflow-y-auto shadow-2xl flex flex-col">

          {/* ── Sticky header ──────────────────────────────────────────────── */}
          <div className="sticky top-0 z-10 bg-white border-b border-slate-100 px-6 py-4 flex items-center gap-4">
            {/* Left */}
            <button
              onClick={onClose}
              className="text-sm text-slate-500 hover:text-slate-800 font-medium flex items-center gap-1 flex-shrink-0"
            >
              ← Back
            </button>
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <span className="font-bold text-slate-800 text-base truncate">{policy.name}</span>
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border flex-shrink-0 ${
                policy.is_active
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-slate-50 text-slate-500 border-slate-200'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${policy.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                {policy.is_active ? 'Active' : 'Paused'}
              </span>
            </div>

            {/* Right: actions */}
            <div className="flex items-center gap-2 flex-shrink-0">
              {backupResult && (
                <span className={`text-xs px-2.5 py-1 rounded-lg ${backupResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                  {backupResult.ok ? '✓' : '✕'} {backupResult.msg}
                </span>
              )}
              <button
                onClick={handleBackupNow}
                disabled={triggering}
                className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-60 text-white rounded-lg text-xs font-semibold transition-colors"
              >
                {triggering ? 'Queuing…' : '↑ Backup Now'}
              </button>
              <button
                onClick={() => setEditOpen(true)}
                className="px-3 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-lg text-xs font-medium transition-colors"
              >
                Edit
              </button>
              <button
                onClick={handleToggle}
                disabled={toggling}
                className={`px-3 py-1.5 border rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
                  policy.is_active
                    ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
                    : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                }`}
              >
                {toggling ? '…' : policy.is_active ? 'Pause' : 'Resume'}
              </button>
              <button
                onClick={handleDeletePolicy}
                disabled={deleting}
                className="px-3 py-1.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
              >
                {deleting ? '…' : 'Delete'}
              </button>
            </div>
          </div>

          {/* ── Info cards ─────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 px-6 py-5">
            {/* Schedule */}
            <div className="bg-white border border-slate-100 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">📅</span>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Schedule</span>
              </div>
              <div className="font-semibold text-slate-800 text-sm">{policy.schedule_description ?? policy.schedule}</div>
              <code className="text-xs text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded font-mono mt-1 inline-block">{policy.schedule}</code>
            </div>

            {/* Retention */}
            <div className="bg-white border border-slate-100 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">🗑</span>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Retention</span>
              </div>
              <div className="font-semibold text-slate-800 text-sm">{policy.retention_days} days</div>
            </div>

            {/* VMs */}
            <div className="bg-white border border-slate-100 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">🖥</span>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Protected</span>
              </div>
              <div className="font-semibold text-slate-800 text-sm">{vmCount} VM{vmCount !== 1 ? 's' : ''} protected</div>
            </div>

            {/* Backup Type */}
            <div className="bg-white border border-slate-100 rounded-xl p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">△</span>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Backup Type</span>
              </div>
              {policy.incremental_enabled ? (
                <div className="font-semibold text-slate-800 text-sm">
                  Incremental / Full every {policy.full_backup_interval} runs
                </div>
              ) : (
                <div className="font-semibold text-slate-800 text-sm">Full Only</div>
              )}
            </div>

            {/* GFS */}
            {policy.gfs_enabled && (
              <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 shadow-sm col-span-2 lg:col-span-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">🗂</span>
                  <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">GFS Retention (Grandfather-Father-Son)</span>
                </div>
                <div className="flex gap-6 text-sm">
                  <div><span className="text-indigo-400">Daily:</span> <strong className="text-indigo-700">{policy.gfs_daily} days</strong></div>
                  <div><span className="text-indigo-400">Weekly:</span> <strong className="text-indigo-700">{policy.gfs_weekly} weeks</strong></div>
                  <div><span className="text-indigo-400">Monthly:</span> <strong className="text-indigo-700">{policy.gfs_monthly} months</strong></div>
                  <div className="ml-auto text-indigo-400 text-xs">~{(policy.gfs_daily||7) + (policy.gfs_weekly||4) + (policy.gfs_monthly||12)} recovery points kept</div>
                </div>
              </div>
            )}
          </div>

          {/* ── Recovery Points ─────────────────────────────────────────────── */}
          <div className="px-6 flex-1">
            {/* Section header */}
            <div className="flex items-center gap-3 mb-3">
              <h3 className="font-bold text-slate-800 text-sm">Recovery Points</h3>
              <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs font-semibold">
                {sortedBackups.length}
              </span>
            </div>

            {/* Bulk action bar */}
            {selected.size > 0 && (
              <div className="flex items-center gap-3 mb-3 px-4 py-2.5 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-xs font-medium text-slate-600">{selected.size} selected</span>
                <button
                  onClick={handleBulkDelete}
                  disabled={bulkDeleting}
                  className="px-3 py-1.5 bg-red-600 hover:bg-red-500 disabled:opacity-60 text-white rounded-lg text-xs font-semibold transition-colors"
                >
                  {bulkDeleting ? 'Deleting…' : 'Delete Selected'}
                </button>
                <button
                  onClick={() => setSelected(new Set())}
                  className="ml-auto text-xs text-slate-400 hover:text-slate-600"
                >
                  Clear
                </button>
              </div>
            )}

            {sortedBackups.length === 0 ? (
              <div className="text-center py-12 text-slate-300">
                <div className="text-3xl mb-2">⊘</div>
                <p className="text-sm">No recovery points yet.</p>
              </div>
            ) : (
              <div className="bg-white border border-slate-100 rounded-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        <th className="px-4 py-2.5 w-8">
                          <input
                            type="checkbox"
                            checked={selected.size === sortedBackups.length && sortedBackups.length > 0}
                            onChange={toggleSelectAll}
                            className="rounded border-slate-300"
                          />
                        </th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">VM Name</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Type</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Encryption</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Status</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Size</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Expires At</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Started</th>
                        <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedBackups.map(job => {
                        const isAvailable = (job.recovery_status ?? job.status ?? '').toLowerCase() === 'available'
                          || (job.recovery_status ?? job.status ?? '').toLowerCase() === 'success'
                        return (
                          <tr key={job.id} className="border-b border-slate-50 hover:bg-slate-50/50">
                            <td className="px-4 py-2">
                              <input
                                type="checkbox"
                                checked={selected.has(job.id)}
                                onChange={() => toggleSelect(job.id)}
                                className="rounded border-slate-300"
                              />
                            </td>
                            <td className="px-4 py-2 font-medium text-slate-700 font-mono">
                              {job.vm_name ?? job.vm_id ?? '—'}
                            </td>
                            <td className="px-4 py-2">
                              <TypeBadge job={job} />
                            </td>
                            <td className="px-4 py-2">
                              {job.encrypted === true && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-200">
                                  🔒 AES-256
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-2">
                              <RecoveryStatusBadge status={job.recovery_status ?? job.status} />
                            </td>
                            <td className="px-4 py-2 text-slate-500">
                              {job.size_gb != null ? `${parseFloat(job.size_gb).toFixed(2)} GB` : '—'}
                            </td>
                            <td className="px-4 py-2 text-slate-400 font-mono whitespace-nowrap">
                              {job.expires_at ? new Date(job.expires_at).toLocaleString() : '—'}
                            </td>
                            <td className="px-4 py-2 text-slate-400 font-mono whitespace-nowrap">
                              {job.started_at ? new Date(job.started_at).toLocaleString() : '—'}
                            </td>
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-1.5">
                                {isAvailable && (
                                  <button
                                    onClick={() => setRestoreTarget(job)}
                                    className="px-2 py-1 bg-amber-500 hover:bg-amber-400 text-white rounded text-xs font-semibold transition-colors"
                                  >
                                    Restore
                                  </button>
                                )}
                                <button
                                  onClick={() => handleDeleteBackup(job.id)}
                                  disabled={deletingId === job.id}
                                  className="px-2 py-1 border border-red-200 text-red-600 hover:bg-red-50 rounded text-xs font-medium transition-colors disabled:opacity-50"
                                >
                                  {deletingId === job.id ? '…' : 'Delete'}
                                </button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* ── Restore History ─────────────────────────────────────────────── */}
          <div className="px-6 pb-6 mt-5">
            <button
              onClick={() => setShowRestores(v => !v)}
              className="w-full flex items-center justify-between px-5 py-3 bg-white border border-slate-100 rounded-xl shadow-sm text-xs font-medium text-slate-500 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-700 text-sm">Restore History</span>
                <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs font-semibold">{pRestores.length}</span>
              </div>
              <span className="text-slate-300">{showRestores ? '▲' : '▼'}</span>
            </button>

            {showRestores && (
              <div className="mt-2 space-y-2">
                {pRestores.length === 0 ? (
                  <p className="text-xs text-slate-300 py-4 text-center">No restore jobs for this policy.</p>
                ) : (
                  pRestores.map(r => (
                    <div key={r.id} className="flex items-center justify-between bg-white border border-slate-100 rounded-xl px-4 py-3 text-xs shadow-sm">
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-slate-700 truncate">{r.target_vm_name ?? '—'}</div>
                        <div className="text-slate-400 font-mono truncate mt-0.5">{r.id?.substring(0, 16)}…</div>
                      </div>
                      <div className="ml-3 flex-shrink-0">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${
                          r.status === 'success'   ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                          r.status === 'failed'    ? 'bg-red-50 text-red-600 border-red-200' :
                          r.status === 'running'   ? 'bg-blue-50 text-blue-700 border-blue-200' :
                          'bg-slate-100 text-slate-500 border-slate-200'
                        }`}>
                          {r.status}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Restore Modal */}
      {restoreTarget && (
        <RestoreModal
          backup={restoreTarget}
          onClose={() => setRestoreTarget(null)}
          onSuccess={() => { setRestoreTarget(null); onRefresh() }}
        />
      )}

      {/* Edit Policy Modal */}
      {editOpen && (
        <PolicyModal
          policy={policy}
          onClose={() => setEditOpen(false)}
          onSaved={() => { setEditOpen(false); onRefresh() }}
        />
      )}
    </>
  )
}
