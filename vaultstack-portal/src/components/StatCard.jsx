export default function StatCard({ icon, label, value, sub, color = 'blue' }) {
  const colors = {
    blue:   'bg-blue-50 text-blue-600',
    green:  'bg-emerald-50 text-emerald-600',
    red:    'bg-red-50 text-red-600',
    amber:  'bg-amber-50 text-amber-600',
    purple: 'bg-purple-50 text-purple-600',
    slate:  'bg-slate-100 text-slate-600',
  }
  return (
    <div className="bg-white rounded-xl border border-slate-100 p-5 flex items-center gap-4 shadow-sm">
      <div className={`w-11 h-11 rounded-lg flex items-center justify-center text-xl flex-shrink-0 ${colors[color]}`}>
        {icon}
      </div>
      <div>
        <div className="text-2xl font-bold text-slate-800 leading-none">{value ?? '—'}</div>
        <div className="text-xs text-slate-400 mt-1">{label}</div>
        {sub && <div className="text-xs text-slate-300 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}
