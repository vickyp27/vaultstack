import { useEffect } from 'react'
import { formatDate } from '../utils'

export default function ErrorModal({ job, onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  if (!job) return null
  const isRestore = 'target_vm_name' in job

  const rows = [
    ['Job ID',     job.id],
    [isRestore ? 'Target VM' : 'VM Name', job.vm_name ?? job.target_vm_name ?? '—'],
    ['Status',     job.status],
    ['Started',    formatDate(job.started_at)],
    ['Completed',  formatDate(job.completed_at)],
    ...(job.size_gb != null ? [['Size', `${job.size_gb} GB`]] : []),
    ...(job.backup_path ? [['Backup Path', job.backup_path]] : []),
    ...(job.new_vm_id ? [['New VM ID', job.new_vm_id]] : []),
  ]

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-red-50 border-b border-red-100">
          <div className="flex items-center gap-2 text-red-700 font-semibold">
            <span className="text-lg">⚠</span>
            Job Failure Detail
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
        </div>

        {/* Detail rows */}
        <div className="px-6 pt-4 pb-2">
          {rows.map(([k, v]) => v && v !== '—' && (
            <div key={k} className="flex gap-3 py-2 border-b border-slate-50 last:border-0 text-sm">
              <span className="w-28 flex-shrink-0 text-slate-400">{k}</span>
              <span className="text-slate-700 font-medium break-all">{v}</span>
            </div>
          ))}
        </div>

        {/* Error message */}
        {job.error_msg && (
          <div className="px-6 pb-5">
            <div className="text-xs text-slate-400 font-semibold uppercase tracking-wide mb-2 mt-3">Error Message</div>
            <pre className="bg-slate-900 text-red-300 rounded-xl p-4 text-xs overflow-auto max-h-52 leading-relaxed whitespace-pre-wrap break-words">
              {job.error_msg}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
