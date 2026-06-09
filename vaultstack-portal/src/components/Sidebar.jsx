import { NavLink } from 'react-router-dom'
import clsx from 'clsx'

const NAV = [
  {
    group: 'INFRASTRUCTURE',
    items: [
      { to: '/infrastructure', icon: '⊛', label: 'Infrastructure' },
      { to: '/workloads',      icon: '≡', label: 'Workloads'      },
    ],
  },
  {
    group: 'PROTECTION',
    items: [
      { to: '/policies',  icon: '⊕', label: 'Protection Groups' },
      { to: '/jobs',      icon: '↑', label: 'Backup Jobs'       },
      { to: '/restores',  icon: '↩', label: 'Restore Jobs'      },
    ],
  },
  {
    group: 'PLATFORM',
    items: [
      { to: '/',           icon: '▦', label: 'Overview'       },
      { to: '/monitoring', icon: '◉', label: 'Monitoring'     },
      { to: '/tenants',    icon: '⊞', label: 'Tenant Storage' },
    ],
  },
]

export default function Sidebar({ apiOk }) {
  return (
    <aside className="w-60 flex-shrink-0 flex flex-col h-screen" style={{ background: 'linear-gradient(180deg, #0f172a 0%, #111827 100%)' }}>

      {/* Brand */}
      <div className="px-5 py-5 border-b border-white/[0.06]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg flex-shrink-0"
               style={{ background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' }}>
            🛡
          </div>
          <div>
            <div className="text-white font-bold text-sm tracking-tight">VaultStack</div>
            <div className="text-slate-500 text-xs mt-0.5">Operations Portal</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 overflow-y-auto space-y-5 px-3">
        {NAV.map(({ group, items }) => (
          <div key={group}>
            <div className="px-2 mb-1.5 text-[10px] font-bold tracking-widest text-slate-600 uppercase">
              {group}
            </div>
            <div className="space-y-0.5">
              {items.map(({ to, icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) => clsx(
                    'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-150',
                    isActive
                      ? 'text-white font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.05]'
                  )}
                  style={({ isActive }) => isActive
                    ? { background: 'linear-gradient(135deg, rgba(99,102,241,0.3) 0%, rgba(139,92,246,0.15) 100%)', boxShadow: 'inset 0 0 0 1px rgba(99,102,241,0.3)' }
                    : {}}
                >
                  <span className="text-sm w-5 text-center opacity-80">{icon}</span>
                  <span className="truncate">{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-white/[0.06] space-y-2">
        <div className="flex items-center gap-2 px-2">
          <span className={clsx(
            'w-2 h-2 rounded-full flex-shrink-0',
            apiOk === null ? 'bg-slate-500' :
            apiOk ? 'bg-emerald-400 pulse-dot' : 'bg-red-500'
          )} />
          <span className="text-xs text-slate-500">
            {apiOk === null ? 'Connecting…' : apiOk ? 'API connected' : 'API unreachable'}
          </span>
        </div>
      </div>
    </aside>
  )
}
