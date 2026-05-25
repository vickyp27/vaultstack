import Badge from '../components/Badge'
import { formatDate, formatSize } from '../utils'

export default function Workloads({ data }) {
  const { workloads, policies } = data
  const policyMap = Object.fromEntries(policies.map(p => [p.id, p.name]))

  return (
    <div className="p-6">
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">Workload Snapshots</span>
          <span className="text-xs text-slate-400">{workloads.length} total</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-50">
                {['Policy', 'Status', 'VMs', 'Size', 'Started', 'Completed'].map(h => (
                  <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-5 py-2.5 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {workloads.length === 0 && (
                <tr><td colSpan={6} className="text-center py-12 text-slate-300">No workload snapshots yet.</td></tr>
              )}
              {workloads.map(w => {
                const done   = w.completed_count ?? 0
                const total  = w.vm_count ?? 0
                const failed = w.failed_count ?? 0
                const pct    = total ? Math.round(done / total * 100) : 0
                return (
                  <tr key={w.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3">
                      <div className="font-medium text-slate-800">{w.policy_name ?? policyMap[w.policy_id] ?? '—'}</div>
                      <div className="text-xs text-slate-400 font-mono">{w.id?.substring(0, 8)}…</div>
                    </td>
                    <td className="px-5 py-3"><Badge status={w.status} /></td>
                    <td className="px-5 py-3 w-44">
                      {total > 0 ? (
                        <>
                          <div className="flex justify-between text-xs text-slate-400 mb-1">
                            <span>
                              {done}/{total} VMs
                              {failed > 0 && <span className="text-red-500 ml-1">({failed} failed)</span>}
                            </span>
                            <span>{pct}%</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${failed > 0 ? 'bg-amber-400' : 'bg-emerald-400'}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </>
                      ) : '—'}
                    </td>
                    <td className="px-5 py-3 text-slate-600">{formatSize(w.total_size_gb)}</td>
                    <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(w.started_at)}</td>
                    <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(w.completed_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
