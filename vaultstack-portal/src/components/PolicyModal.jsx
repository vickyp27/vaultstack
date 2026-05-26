import { useState, useEffect } from 'react'
import { api } from '../api'

const SCHEDULES = [
  { value: '0 2 * * *',   label: 'Daily at 2:00 AM' },
  { value: '0 0 * * *',   label: 'Daily at midnight' },
  { value: '0 */6 * * *', label: 'Every 6 hours' },
  { value: '0 */4 * * *', label: 'Every 4 hours' },
  { value: '0 */2 * * *', label: 'Every 2 hours' },
  { value: '0 2 * * 0',   label: 'Weekly — Sunday at 2 AM' },
  { value: '0 2 * * 1',   label: 'Weekly — Monday at 2 AM' },
  { value: '0 2 1 * *',   label: 'Monthly — 1st at 2 AM' },
  { value: '__custom__',   label: 'Custom cron…' },
]

const EMPTY = {
  name: '',
  vm_ids: [],
  schedule: '0 2 * * *',
  customSchedule: '',
  retention_days: 30,
  incremental_enabled: false,
  full_backup_interval: 6,
}

export default function PolicyModal({ policy, onClose, onSaved }) {
  const isEdit = !!policy
  const [vms, setVms]       = useState([])
  const [form, setForm]     = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')

  useEffect(() => {
    api.vms().then(list => setVms(list ?? [])).catch(() => setVms([]))
  }, [])

  useEffect(() => {
    if (!policy) { setForm(EMPTY); return }
    const knownSchedule = SCHEDULES.find(s => s.value === policy.schedule && s.value !== '__custom__')
    setForm({
      name: policy.name,
      vm_ids: policy.vm_ids ?? [],
      schedule: knownSchedule ? policy.schedule : '__custom__',
      customSchedule: knownSchedule ? '' : policy.schedule,
      retention_days: policy.retention_days ?? 30,
      incremental_enabled: policy.incremental_enabled ?? false,
      full_backup_interval: policy.full_backup_interval ?? 6,
    })
  }, [policy])

  function set(key, val) {
    setForm(f => ({ ...f, [key]: val }))
  }

  function toggleVm(id) {
    set('vm_ids', form.vm_ids.includes(id)
      ? form.vm_ids.filter(v => v !== id)
      : [...form.vm_ids, id]
    )
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    const schedule = form.schedule === '__custom__' ? form.customSchedule.trim() : form.schedule
    if (!form.name.trim()) return setError('Name is required')
    if (!schedule) return setError('Schedule is required')
    if (form.vm_ids.length === 0) return setError('Select at least one VM')

    const body = {
      name: form.name.trim(),
      vm_ids: form.vm_ids,
      schedule,
      retention_days: Number(form.retention_days),
      incremental_enabled: form.incremental_enabled,
      full_backup_interval: Number(form.full_backup_interval),
    }

    setSaving(true)
    try {
      if (isEdit) {
        await api.updatePolicy(policy.id, body)
      } else {
        await api.createPolicy(body)
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="font-bold text-slate-800 text-base">
            {isEdit ? 'Edit Protection Group' : 'New Protection Group'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Name */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Name</label>
            <input
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="e.g. Production VMs"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200"
            />
          </div>

          {/* Schedule */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Schedule</label>
            <select
              value={form.schedule}
              onChange={e => set('schedule', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-200 bg-white"
            >
              {SCHEDULES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            {form.schedule === '__custom__' && (
              <input
                value={form.customSchedule}
                onChange={e => set('customSchedule', e.target.value)}
                placeholder="0 3 * * 1-5"
                className="mt-2 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-200"
              />
            )}
          </div>

          {/* Retention */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Retention — <span className="text-slate-400 font-normal">{form.retention_days} days</span>
            </label>
            <input
              type="range" min="1" max="365" step="1"
              value={form.retention_days}
              onChange={e => set('retention_days', e.target.value)}
              className="w-full accent-sky-500"
            />
            <div className="flex justify-between text-xs text-slate-400 mt-1">
              <span>1 day</span><span>365 days</span>
            </div>
          </div>

          {/* Incremental */}
          <div className="bg-slate-50 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-slate-700">Incremental Backup</div>
                <div className="text-xs text-slate-400 mt-0.5">Store only changed blocks between runs</div>
              </div>
              <button
                type="button"
                onClick={() => set('incremental_enabled', !form.incremental_enabled)}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  form.incremental_enabled ? 'bg-sky-500' : 'bg-slate-300'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                  form.incremental_enabled ? 'translate-x-5' : ''
                }`} />
              </button>
            </div>

            {form.incremental_enabled && (
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  Full backup every <span className="text-sky-600">{form.full_backup_interval}</span> runs
                </label>
                <input
                  type="range" min="2" max="30" step="1"
                  value={form.full_backup_interval}
                  onChange={e => set('full_backup_interval', e.target.value)}
                  className="w-full accent-sky-500"
                />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>2 runs</span><span>30 runs</span>
                </div>
              </div>
            )}
          </div>

          {/* VM selection */}
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              VMs to protect — <span className="text-slate-400 font-normal">{form.vm_ids.length} selected</span>
            </label>
            {vms.length === 0 ? (
              <p className="text-xs text-slate-400 py-3 text-center border border-slate-100 rounded-lg">
                No VMs found (OpenStack may be unreachable)
              </p>
            ) : (
              <div className="border border-slate-200 rounded-lg divide-y divide-slate-50 max-h-48 overflow-y-auto">
                {vms.map(vm => (
                  <label key={vm.id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-slate-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.vm_ids.includes(vm.id)}
                      onChange={() => toggleVm(vm.id)}
                      className="accent-sky-500"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-slate-700 truncate">{vm.name}</div>
                      <div className="text-xs text-slate-400 font-mono truncate">{vm.id}</div>
                    </div>
                    <span className={`flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full font-medium ${
                      vm.status === 'ACTIVE'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}>{vm.status}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {error && <p className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="px-5 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Policy'}
          </button>
        </div>
      </div>
    </div>
  )
}
