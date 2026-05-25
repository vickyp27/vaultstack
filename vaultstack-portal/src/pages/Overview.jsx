import { useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import ErrorModal from '../components/ErrorModal'
import { formatDate, formatSize } from '../utils'

export default function Overview({ data }) {
  const [errorJob, setErrorJob] = useState(null)
  const { backups, restores, policies, stats } = data

  const totalSize = backups.reduce((a, j) => a + (parseFloat(j.size_gb) || 0), 0).toFixed(2)
  const liveJobs  = [...backups, ...restores].filter(j => ['running', 'queued'].includes(j.status))
  const recent    = backups.slice(0, 10)

  // Last 7 days chart data
  const chartData = (() => {
    const days = {}
    for (let i = 6; i >= 0; i--) {
      const d = new Date(); d.setDate(d.getDate() - i)
      const key = d.toLocaleDateString('en', { month: 'short', day: 'numeric' })
      days[key] = { date: key, success: 0, failed: 0 }
    }
    backups.forEach(j => {
      try {
        const d = new Date(j.started_at.replace(' ', 'T') + 'Z')
        const key = d.toLocaleDateString('en', { month: 'short', day: 'numeric' })
        if (days[key]) days[key][j.status === 'success' ? 'success' : 'failed']++
      } catch { /* ignore */ }
    })
    return Object.values(days)
  })()

  return (
    <div className="p-6 space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard icon="☁" label="Total Backups"   value={backups.length}                                          color="blue"   />
        <StatCard icon="✓" label="Successful"       value={backups.filter(j => j.status === 'success').length}     color="green"  />
        <StatCard icon="✕" label="Failed"           value={backups.filter(j => j.status === 'failed').length}      color="red"    />
        <StatCard icon="⟳" label="Running / Queued" value={liveJobs.length}                                        color="amber"  />
        <StatCard icon="◫" label="Storage Used"     value={`${totalSize} GB`}                                      color="purple" />
        <StatCard icon="⊕" label="Active Policies"  value={policies.filter(p => p.is_active).length}               color="slate"  />
      </div>

      {/* Live jobs */}
      {liveJobs.length > 0 && (
        <div className="bg-white rounded-xl border border-blue-100 shadow-sm overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3.5 bg-blue-50 border-b border-blue-100">
            <span className="w-2 h-2 rounded-full bg-blue-500 pulse-dot" />
            <span className="text-sm font-semibold text-blue-700">Live Jobs ({liveJobs.length})</span>
          </div>
          <div className="divide-y divide-slate-50">
            {liveJobs.map(j => (
              <div key={j.id} className="flex items-center gap-4 px-5 py-3">
                <Badge status={j.status} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-slate-800 truncate">
                    {j.vm_name ?? j.target_vm_name ?? '—'}
                  </div>
                  <div className="text-xs text-slate-400">
                    {'target_vm_name' in j ? 'Restore' : 'Backup'} · started {formatDate(j.started_at)}
                  </div>
                </div>
                {j.progress != null && (
                  <div className="w-36">
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>{j.progress_msg ?? ''}</span>
                      <span>{j.progress}%</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full transition-all duration-500" style={{ width: `${j.progress}%` }} />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Chart */}
        <div className="xl:col-span-2 bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <div className="text-sm font-semibold text-slate-700 mb-4">Backup Activity — Last 7 Days</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="success" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="failed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #f1f5f9', fontSize: 12 }}
                labelStyle={{ fontWeight: 600, color: '#1e293b' }}
              />
              <Area type="monotone" dataKey="success" stroke="#10b981" strokeWidth={2} fill="url(#success)" name="Success" />
              <Area type="monotone" dataKey="failed"  stroke="#ef4444" strokeWidth={2} fill="url(#failed)"  name="Failed" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Policy summary */}
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <div className="text-sm font-semibold text-slate-700 mb-4">Protection Groups</div>
          <div className="space-y-3">
            {policies.length === 0 && <p className="text-xs text-slate-400">No policies found.</p>}
            {policies.map(p => (
              <div key={p.id} className="flex items-start gap-3">
                <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${p.is_active ? 'bg-emerald-400' : 'bg-slate-300'}`} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-800 truncate">{p.name}</div>
                  <div className="text-xs text-slate-400">{p.schedule_description ?? p.schedule}</div>
                  {p.next_run && <div className="text-xs text-slate-300 mt-0.5">Next: {p.next_run}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent backup jobs */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">Recent Backup Jobs</span>
          <span className="text-xs text-slate-400">{recent.length} shown</span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-50">
              {['VM', 'Status', 'Size', 'Started', 'Error'].map(h => (
                <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-5 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {recent.length === 0 && (
              <tr><td colSpan={5} className="text-center py-10 text-slate-300 text-sm">No backup jobs yet.</td></tr>
            )}
            {recent.map(j => (
              <tr key={j.id} className="hover:bg-slate-50/60 transition-colors">
                <td className="px-5 py-3">
                  <div className="font-medium text-slate-800">{j.vm_name ?? '—'}</div>
                  <div className="text-xs text-slate-400 font-mono truncate max-w-[160px]">{j.vm_id}</div>
                </td>
                <td className="px-5 py-3"><Badge status={j.status} /></td>
                <td className="px-5 py-3 text-slate-600">{formatSize(j.size_gb)}</td>
                <td className="px-5 py-3 text-slate-400 whitespace-nowrap text-xs">{formatDate(j.started_at)}</td>
                <td className="px-5 py-3">
                  {j.error_msg
                    ? <button onClick={() => setErrorJob(j)} className="text-red-500 hover:text-red-700 text-xs underline decoration-dotted text-left">
                        {j.error_msg.substring(0, 48)}{j.error_msg.length > 48 ? '…' : ''}
                      </button>
                    : <span className="text-slate-300">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ErrorModal job={errorJob} onClose={() => setErrorJob(null)} />
    </div>
  )
}
