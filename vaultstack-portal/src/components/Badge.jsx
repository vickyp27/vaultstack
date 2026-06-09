import clsx from 'clsx'

const STATUS = {
  success:  { cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200/70', dot: 'bg-emerald-500', label: 'Success'  },
  failed:   { cls: 'bg-red-50 text-red-600 ring-red-200/70',             dot: 'bg-red-500',     label: 'Failed'   },
  running:  { cls: 'bg-blue-50 text-blue-700 ring-blue-200/70',          dot: null, spin: true,  label: 'Running'  },
  queued:   { cls: 'bg-slate-100 text-slate-500 ring-slate-200/70',      dot: 'bg-slate-400',   label: 'Queued'   },
  partial:  { cls: 'bg-amber-50 text-amber-700 ring-amber-200/70',       dot: 'bg-amber-500',   label: 'Partial'  },
  expired:  { cls: 'bg-slate-100 text-slate-400 ring-slate-200/70',      dot: 'bg-slate-300',   label: 'Expired'  },
}

export default function Badge({ status }) {
  const s = STATUS[status] ?? STATUS.queued
  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ring-1',
      s.cls
    )}>
      {s.spin
        ? <span className="w-2.5 h-2.5 rounded-full border-2 border-current border-t-transparent spin" />
        : <span className={clsx('w-1.5 h-1.5 rounded-full', s.dot)} />
      }
      {s.label}
    </span>
  )
}
