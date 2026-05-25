import { useState } from 'react'
import Badge from '../components/Badge'
import ErrorModal from '../components/ErrorModal'
import { formatDate } from '../utils'

export default function RestoreJobs({ data }) {
  const [errorJob, setErrorJob] = useState(null)
  const { restores } = data

  return (
    <div className="p-6">
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">Restore Jobs</span>
          <span className="text-xs text-slate-400">{restores.length} total</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-50">
                {['Target VM', 'Status', 'Progress', 'New VM ID', 'Started', 'Error'].map(h => (
                  <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-5 py-2.5 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {restores.length === 0 && (
                <tr><td colSpan={6} className="text-center py-12 text-slate-300">No restore jobs yet.</td></tr>
              )}
              {restores.map(j => {
                const pct    = j.progress ?? 0
                const isLive = ['running', 'queued'].includes(j.status)
                return (
                  <tr key={j.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3 font-medium text-slate-800">{j.target_vm_name ?? '—'}</td>
                    <td className="px-5 py-3"><Badge status={j.status} /></td>
                    <td className="px-5 py-3 w-48">
                      <div className="flex justify-between text-xs text-slate-400 mb-1">
                        <span className="truncate max-w-[110px]">{j.progress_msg ?? (j.status === 'success' ? 'Complete' : j.status)}</span>
                        <span className="ml-2">{pct}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            j.status === 'success' ? 'bg-emerald-400' :
                            j.status === 'failed'  ? 'bg-red-400'     : 'bg-blue-400'
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {j.new_vm_id
                        ? <span className="font-mono text-xs text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded">{j.new_vm_id.substring(0, 12)}…</span>
                        : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(j.started_at)}</td>
                    <td className="px-5 py-3">
                      {j.error_msg
                        ? <button onClick={() => setErrorJob(j)} className="flex items-center gap-1 text-red-500 hover:text-red-700 text-xs text-left">
                            <span className="text-base leading-none">⚠</span>
                            <span className="underline decoration-dotted max-w-[140px] truncate">{j.error_msg}</span>
                          </button>
                        : <span className="text-slate-300">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <ErrorModal job={errorJob} onClose={() => setErrorJob(null)} />
    </div>
  )
}
