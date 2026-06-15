import { useState, useEffect } from 'react'
import { api } from '../api'

const STATUS_STYLE = {
  compliant: { cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Compliant' },
  at_risk:   { cls: 'bg-amber-50  text-amber-700  border-amber-200',  label: 'At Risk'   },
  breach:    { cls: 'bg-red-50    text-red-600    border-red-200',    label: 'Breach'    },
}

function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.compliant
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${s.cls}`}>
      {s.label}
    </span>
  )
}

function SummaryCard({ label, value, color }) {
  return (
    <div className={`bg-white rounded-xl border shadow-sm px-5 py-4 ${color}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  )
}

export default function SLA() {
  const [items,   setItems]   = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [compliance, sum] = await Promise.all([
        api.slaCompliance(),
        api.slaSummary(),
      ])
      setItems(compliance ?? [])
      setSummary(sum)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-6 space-y-6">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <SummaryCard label="Total VMs" value={summary.total} color="border-slate-100" />
          <SummaryCard label="Compliant"  value={summary.compliant} color="border-emerald-100 text-emerald-700" />
          <SummaryCard label="At Risk"    value={summary.at_risk}   color="border-amber-100  text-amber-700" />
          <SummaryCard label="Breach"     value={summary.breach}    color="border-red-100    text-red-600" />
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
          <span className="text-sm font-semibold text-slate-700">SLA Compliance per VM</span>
          <button
            onClick={load}
            className="text-xs text-sky-500 hover:text-sky-700 font-medium"
          >
            ⟳ Refresh
          </button>
        </div>

        {loading ? (
          <div className="py-16 text-center text-slate-400">Loading…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-50">
                  {['VM', 'Policy', 'Status', 'Last Backup', 'Age (hrs)', 'SLA Max (hrs)'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 py-2.5 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-12 text-slate-300">
                      No SLA policies configured. Set <strong>SLA Max Age Hours</strong> in a Protection Group to enable monitoring.
                    </td>
                  </tr>
                )}
                {items.map(item => (
                  <tr key={item.vm_id} className="hover:bg-slate-50/60">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-800">{item.vm_name ?? item.vm_id}</div>
                      <div className="text-xs text-slate-400 font-mono">{item.vm_id?.substring(0, 8)}…</div>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{item.policy_name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">
                      {item.last_backup_at ? new Date(item.last_backup_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {item.age_hours != null ? (
                        <span className={item.status === 'breach' ? 'text-red-600 font-semibold' : item.status === 'at_risk' ? 'text-amber-600 font-semibold' : ''}>
                          {item.age_hours}h
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{item.sla_max_age_hours}h</td>
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
