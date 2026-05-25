import clsx from 'clsx'

const STATUS = {
  success: { bg: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: '✓' },
  failed:  { bg: 'bg-red-50 text-red-700 border-red-200',             icon: '✕' },
  running: { bg: 'bg-blue-50 text-blue-700 border-blue-200',          icon: null, spin: true },
  queued:  { bg: 'bg-slate-100 text-slate-600 border-slate-200',      icon: '○' },
  partial: { bg: 'bg-amber-50 text-amber-700 border-amber-200',       icon: '~' },
}

export default function Badge({ status }) {
  const s = STATUS[status] ?? STATUS.queued
  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border', s.bg)}>
      {s.spin
        ? <span className="w-2.5 h-2.5 rounded-full border-2 border-current border-t-transparent spin" />
        : <span>{s.icon}</span>}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}
