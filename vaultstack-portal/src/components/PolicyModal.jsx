import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'

const SCHEDULES = [
  { value: '0 2 * * *',   label: 'Daily at 2:00 AM' },
  { value: '0 0 * * *',   label: 'Daily at midnight' },
  { value: '0 */6 * * *', label: 'Every 6 hours' },
  { value: '0 */4 * * *', label: 'Every 4 hours' },
  { value: '0 */2 * * *', label: 'Every 2 hours' },
  { value: '0 2 * * 0',   label: 'Weekly — Sunday 2 AM' },
  { value: '0 2 * * 1',   label: 'Weekly — Monday 2 AM' },
  { value: '0 2 1 * *',   label: 'Monthly — 1st at 2 AM' },
  { value: '__custom__',   label: 'Custom cron…' },
]

const EMPTY = {
  name: '', vm_ids: [], schedule: '0 2 * * *', customSchedule: '',
  retention_days: 30, incremental_enabled: false, full_backup_interval: 6,
}

export default function PolicyModal({ policy, onClose, onSaved }) {
  const isEdit = !!policy
  const [vms,    setVms]    = useState([])
  const [form,   setForm]   = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    api.vms().then(list => setVms(list ?? [])).catch(() => setVms([]))
  }, [])

  useEffect(() => {
    if (!policy) { setForm(EMPTY); return }
    const known = SCHEDULES.find(s => s.value === policy.schedule && s.value !== '__custom__')
    setForm({
      name: policy.name, vm_ids: policy.vm_ids ?? [],
      schedule: known ? policy.schedule : '__custom__',
      customSchedule: known ? '' : policy.schedule,
      retention_days: policy.retention_days ?? 30,
      incremental_enabled: policy.incremental_enabled ?? false,
      full_backup_interval: policy.full_backup_interval ?? 6,
    })
  }, [policy])

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))
  const toggleVm = id => set('vm_ids', form.vm_ids.includes(id)
    ? form.vm_ids.filter(v => v !== id) : [...form.vm_ids, id])

  // Group VMs by project
  const grouped = useMemo(() => {
    const filtered = vms.filter(vm =>
      !search || vm.name.toLowerCase().includes(search.toLowerCase()) ||
      (vm.project_name ?? '').toLowerCase().includes(search.toLowerCase())
    )
    const map = {}
    filtered.forEach(vm => {
      const key = vm.project_name || vm.project_id || 'Unknown Project'
      if (!map[key]) map[key] = []
      map[key].push(vm)
    })
    return map
  }, [vms, search])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    const schedule = form.schedule === '__custom__' ? form.customSchedule.trim() : form.schedule
    if (!form.name.trim()) return setError('Name is required')
    if (!schedule) return setError('Schedule is required')
    if (form.vm_ids.length === 0) return setError('Select at least one VM')
    setSaving(true)
    try {
      const body = {
        name: form.name.trim(), vm_ids: form.vm_ids, schedule,
        retention_days: Number(form.retention_days),
        incremental_enabled: form.incremental_enabled,
        full_backup_interval: Number(form.full_backup_interval),
      }
      isEdit ? await api.updatePolicy(policy.id, body) : await api.createPolicy(body)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[92vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-100 flex items-center justify-center text-indigo-600 text-base font-bold">
              {isEdit ? '✎' : '+'}
            </div>
            <div>
              <h2 className="font-bold text-slate-800 text-sm">{isEdit ? 'Edit Protection Group' : 'New Protection Group'}</h2>
              <p className="text-xs text-slate-400 mt-0.5">{isEdit ? `Editing: ${policy.name}` : 'Configure schedule, retention & VMs'}</p>
            </div>
          </div>
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors text-lg leading-none">&times;</button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Name */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Policy Name</label>
            <input
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="e.g. Production VMs — Nightly"
              className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 placeholder:text-slate-300 transition"
            />
          </div>

          {/* Schedule */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Schedule</label>
            <select
              value={form.schedule}
              onChange={e => set('schedule', e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white transition"
            >
              {SCHEDULES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            {form.schedule === '__custom__' && (
              <input
                value={form.customSchedule}
                onChange={e => set('customSchedule', e.target.value)}
                placeholder="0 3 * * 1-5"
                className="mt-2 w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 transition"
              />
            )}
          </div>

          {/* Retention */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Retention Period</label>
              <span className="text-sm font-bold text-indigo-600">{form.retention_days} days</span>
            </div>
            <input
              type="range" min="1" max="365" step="1"
              value={form.retention_days}
              onChange={e => set('retention_days', e.target.value)}
              className="w-full accent-indigo-500 h-1.5 rounded-full"
            />
            <div className="flex justify-between text-xs text-slate-400 mt-1">
              <span>1 day</span><span>365 days</span>
            </div>
          </div>

          {/* Incremental */}
          <div className="rounded-xl border border-slate-200 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 bg-slate-50">
              <div>
                <div className="text-sm font-semibold text-slate-700">Incremental Backups</div>
                <div className="text-xs text-slate-400 mt-0.5">Store only changed blocks between runs</div>
              </div>
              <button
                type="button"
                onClick={() => set('incremental_enabled', !form.incremental_enabled)}
                className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${form.incremental_enabled ? 'bg-indigo-500' : 'bg-slate-300'}`}
              >
                <span className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200 ${form.incremental_enabled ? 'translate-x-5' : ''}`} />
              </button>
            </div>
            {form.incremental_enabled && (
              <div className="px-4 py-3 border-t border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-500">Full backup every</label>
                  <span className="text-sm font-bold text-indigo-600">{form.full_backup_interval} runs</span>
                </div>
                <input
                  type="range" min="2" max="30" step="1"
                  value={form.full_backup_interval}
                  onChange={e => set('full_backup_interval', e.target.value)}
                  className="w-full accent-indigo-500 h-1.5"
                />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>2 runs</span><span>30 runs</span>
                </div>
              </div>
            )}
          </div>

          {/* VM Selection */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">VMs to Protect</label>
              <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                {form.vm_ids.length} selected
              </span>
            </div>

            {vms.length > 4 && (
              <div className="relative mb-2">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs">🔍</span>
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search VMs or projects…"
                  className="w-full pl-7 pr-3 py-2 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300 transition"
                />
              </div>
            )}

            {vms.length === 0 ? (
              <div className="text-xs text-slate-400 py-8 text-center border border-dashed border-slate-200 rounded-xl">
                <div className="text-2xl mb-2">🖥</div>
                No VMs found — OpenStack may be unreachable
              </div>
            ) : Object.keys(grouped).length === 0 ? (
              <div className="text-xs text-slate-400 py-6 text-center border border-dashed border-slate-200 rounded-xl">
                No VMs match "{search}"
              </div>
            ) : (
              <div className="border border-slate-200 rounded-xl overflow-hidden max-h-52 overflow-y-auto">
                {Object.entries(grouped).map(([project, projectVms]) => (
                  <div key={project}>
                    {/* Project header */}
                    <div className="px-3 py-1.5 bg-slate-50 border-b border-slate-100 flex items-center gap-2 sticky top-0">
                      <span className="text-xs">⊞</span>
                      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{project}</span>
                      <span className="ml-auto text-xs text-slate-400">{projectVms.filter(v => form.vm_ids.includes(v.id)).length}/{projectVms.length}</span>
                    </div>
                    {projectVms.map(vm => (
                      <label key={vm.id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-indigo-50/50 cursor-pointer border-b border-slate-50 last:border-0 transition-colors">
                        <input
                          type="checkbox"
                          checked={form.vm_ids.includes(vm.id)}
                          onChange={() => toggleVm(vm.id)}
                          className="accent-indigo-500 w-3.5 h-3.5"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-slate-700 truncate">{vm.name}</div>
                          <div className="text-xs text-slate-400 font-mono truncate">{vm.id.substring(0, 16)}…</div>
                        </div>
                        <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full font-semibold ${
                          vm.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                        }`}>{vm.status}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-red-600 text-sm">
              <span>⚠</span> {error}
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 bg-slate-50/50">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 font-medium rounded-lg hover:bg-slate-100 transition-colors">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={saving}
            className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50 shadow-sm shadow-indigo-200">
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Policy'}
          </button>
        </div>
      </div>
    </div>
  )
}
