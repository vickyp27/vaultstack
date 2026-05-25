import { useState, useEffect } from 'react'
import { api } from '../api'

export default function RestoreModal({ backup, onClose, onSuccess }) {
  const [vmName,   setVmName]   = useState('')
  const [flavorId, setFlavorId] = useState('')
  const [flavors,  setFlavors]  = useState([])
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  useEffect(() => {
    if (!backup) return
    setVmName(`restored-${backup.vm_name ?? 'vm'}-${Date.now().toString().slice(-4)}`)
    api.flavors().then(list => {
      setFlavors(list ?? [])
      if (list?.length) setFlavorId(list[0].id)
    })
  }, [backup])

  if (!backup) return null

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.createRestore({
        backup_job_id:  backup.id,
        target_vm_name: vmName,
        flavor_id:      flavorId || null,
      })
      onSuccess?.()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-bold text-slate-800">Restore Backup</h2>
            <p className="text-xs text-slate-400 mt-0.5 font-mono truncate max-w-[280px]">{backup.id}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          {/* Source info */}
          <div className="bg-slate-50 rounded-lg px-4 py-3 text-sm">
            <div className="text-xs text-slate-400 mb-1">Restoring from</div>
            <div className="font-medium text-slate-700">{backup.vm_name ?? backup.vm_id}</div>
            <div className="text-xs text-slate-400 font-mono">{backup.backup_path ?? '—'}</div>
          </div>

          {/* New VM name */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1.5">New VM Name</label>
            <input
              type="text"
              value={vmName}
              onChange={e => setVmName(e.target.value)}
              required
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400"
              placeholder="restored-vm-name"
            />
          </div>

          {/* Flavor dropdown */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1.5">Flavor</label>
            {flavors.length === 0 ? (
              <div className="text-xs text-slate-400 py-2">Loading flavors…</div>
            ) : (
              <select
                value={flavorId}
                onChange={e => setFlavorId(e.target.value)}
                required
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400"
              >
                {flavors.map(f => (
                  <option key={f.id} value={f.id}>
                    {f.name} — {f.vcpus} vCPU, {f.ram >= 1024 ? `${f.ram / 1024} GB` : `${f.ram} MB`} RAM
                  </option>
                ))}
              </select>
            )}
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-red-600 text-sm flex items-center gap-2">
              <span>⚠</span> {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-slate-200 rounded-lg py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !flavorId}
              className="flex-1 bg-sky-500 hover:bg-sky-400 disabled:opacity-60 text-white font-semibold rounded-lg py-2 text-sm transition-colors flex items-center justify-center gap-2"
            >
              {loading && <span className="spin inline-block w-4 h-4 border-2 border-white/40 border-t-white rounded-full" />}
              {loading ? 'Starting…' : 'Start Restore'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
