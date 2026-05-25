import { NavLink } from 'react-router-dom'
import clsx from 'clsx'

const NAV = [
  { to: '/',           icon: '▦',  label: 'Overview'          },
  { to: '/jobs',       icon: '↑',  label: 'Backup Jobs'       },
  { to: '/restores',   icon: '↩',  label: 'Restore Jobs'      },
  { to: '/policies',   icon: '⊕',  label: 'Protection Groups' },
  { to: '/workloads',  icon: '≡',  label: 'Workloads'         },
  { to: '/monitoring', icon: '◉',  label: 'Monitoring'        },
  { to: '/tenants',    icon: '⊞',  label: 'Tenant Storage'    },
]

export default function Sidebar({ apiOk }) {
  return (
    <aside className="w-56 flex-shrink-0 bg-[#0f172a] flex flex-col h-screen">
      {/* Brand */}
      <div className="px-5 py-6 border-b border-white/10">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🛡️</span>
          <div>
            <div className="text-white font-bold text-sm tracking-wide">VaultStack</div>
            <div className="text-slate-500 text-xs">Operations Portal</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3">
        {NAV.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => clsx(
              'flex items-center gap-3 px-5 py-2.5 text-sm transition-all border-l-2',
              isActive
                ? 'text-sky-400 bg-sky-400/10 border-sky-400 font-semibold'
                : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-white/5'
            )}
          >
            <span className="text-base w-4 text-center">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* API status */}
      <div className="px-5 py-4 border-t border-white/10">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className={clsx(
            'w-2 h-2 rounded-full flex-shrink-0',
            apiOk === null ? 'bg-slate-500' :
            apiOk ? 'bg-emerald-400 pulse-dot' : 'bg-red-500'
          )} />
          {apiOk === null ? 'Connecting…' : apiOk ? 'API connected' : 'API unreachable'}
        </div>
      </div>
    </aside>
  )
}
