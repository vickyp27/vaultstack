const THEMES = {
  blue:   { border: '#3b82f6', bg: 'rgba(59,130,246,0.08)',  text: '#3b82f6'  },
  green:  { border: '#10b981', bg: 'rgba(16,185,129,0.08)',  text: '#10b981'  },
  red:    { border: '#f43f5e', bg: 'rgba(244,63,94,0.08)',   text: '#f43f5e'  },
  amber:  { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  text: '#f59e0b'  },
  purple: { border: '#8b5cf6', bg: 'rgba(139,92,246,0.08)',  text: '#8b5cf6'  },
  indigo: { border: '#6366f1', bg: 'rgba(99,102,241,0.08)',  text: '#6366f1'  },
  slate:  { border: '#64748b', bg: 'rgba(100,116,139,0.08)', text: '#64748b'  },
}

export default function StatCard({ icon, label, value, sub, color = 'blue', trend }) {
  const t = THEMES[color] ?? THEMES.blue
  return (
    <div
      className="bg-white rounded-2xl p-5 flex flex-col gap-3 relative overflow-hidden transition-shadow hover:shadow-md"
      style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)', border: '1px solid rgba(0,0,0,0.06)' }}
    >
      {/* Accent strip */}
      <div className="absolute top-0 left-0 w-1 h-full rounded-l-2xl" style={{ background: t.border }} />

      <div className="flex items-start justify-between pl-2">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-lg flex-shrink-0"
          style={{ background: t.bg, color: t.text }}
        >
          {icon}
        </div>
        {trend != null && (
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${trend >= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-500'}`}>
            {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%
          </span>
        )}
      </div>

      <div className="pl-2">
        <div className="text-2xl font-extrabold text-slate-800 leading-none tracking-tight">{value ?? '—'}</div>
        <div className="text-xs font-medium text-slate-400 mt-1.5">{label}</div>
        {sub && <div className="text-xs text-slate-300 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}
