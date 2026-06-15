import { useState, useEffect } from 'react'
import { api } from '../api'

export default function RestoreModal({ backup, onClose, onSuccess }) {
  const [vmName,    setVmName]    = useState('')
  const [flavorId,  setFlavorId]  = useState('')
  const [networkId, setNetworkId] = useState('')
  const [flavors,   setFlavors]   = useState([])
  const [networks,  setNetworks]  = useState([])
  const [loading,         setLoading]         = useState(false)
  const [error,           setError]           = useState('')
  const [restoreOriginal, setRestoreOriginal] = useState(false)
  const [singleDisk,      setSingleDisk]      = useState(false)
  const [diskIndices,     setDiskIndices]     = useState('0')

  useEffect(() => {
    if (!backup) return
    setVmName(`restored-${backup.vm_name ?? 'vm'}-${Date.now().toString().slice(-4)}`)

    const providerId = backup.provider_id ?? null

    api.flavors(providerId).then(list => {
      setFlavors(list ?? [])
      if (list?.length) setFlavorId(list[0].id)
    })

    api.networks(backup.project_id, providerId).then(list => {
      setNetworks(list ?? [])
      // Pre-select the original VM's network; fall back to first in list
      const originalNet = backup.network_id
        ? (list ?? []).find(n => n.id === backup.network_id)
        : null
      const defaultNet = originalNet ?? list?.[0]
      if (defaultNet) setNetworkId(defaultNet.id)
    })
  }, [backup])

  if (!backup) return null

  async function handleSubmit(e, instant = false) {
    e.preventDefault()
    setError('')
    setLoading(instant ? 'instant' : 'full')
    try {
      const selectedIndices = singleDisk
        ? diskIndices.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
        : null
      await api.createRestore({
        backup_job_id:            backup.id,
        target_vm_name:           vmName,
        flavor_id:                flavorId || null,
        target_network_id:        networkId || null,
        target_project_id:        backup.project_id || null,
        instant,
        restore_to_original:      restoreOriginal,
        selected_volume_indices:  selectedIndices,
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
            {backup.project_id && (
              <div className="text-xs text-slate-400 font-mono mt-0.5">
                project: {backup.project_id.substring(0, 12)}…
              </div>
            )}
          </div>

          {/* Target project badge */}
          {backup.project_id && (
            <div className="flex items-center gap-2 text-xs bg-sky-50 border border-sky-100 rounded-lg px-3 py-2 text-sky-700">
              <span>⊞</span>
              <span>VM will be restored to the <strong>original project</strong></span>
            </div>
          )}

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

          {/* Flavor */}
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

          {/* Network */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1.5">Network</label>
            {networks.length === 0 ? (
              <div className="text-xs text-slate-400 py-2">Loading networks…</div>
            ) : (
              <select
                value={networkId}
                onChange={e => setNetworkId(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400"
              >
                {networks.map(n => (
                  <option key={n.id} value={n.id}>
                    {n.name}{n.id === backup.network_id ? ' (original)' : ''}
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

          {/* Single Disk Restore */}
          <div className="border border-slate-200 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50">
              <div className="text-xs text-slate-700">
                <strong>Single Disk Restore</strong>
                <span className="text-slate-400 ml-1.5">— restore only selected volume(s)</span>
              </div>
              <button
                type="button"
                onClick={() => setSingleDisk(v => !v)}
                className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ml-4 ${singleDisk ? 'bg-sky-500' : 'bg-slate-200'}`}
              >
                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${singleDisk ? 'left-5' : 'left-0.5'}`} />
              </button>
            </div>
            {singleDisk && (
              <div className="px-4 py-3 border-t border-slate-100">
                <label className="block text-xs text-slate-500 mb-1.5">
                  Volume indices (comma-separated) — 0 = boot, 1 = first data disk, etc.
                </label>
                <input
                  type="text"
                  value={diskIndices}
                  onChange={e => setDiskIndices(e.target.value)}
                  placeholder="0  or  0,1  or  1,2"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-400"
                />
                <p className="text-[10px] text-slate-400 mt-1">
                  Only valid for multi-volume (tar) backups. Single-volume backups ignore this.
                </p>
              </div>
            )}
          </div>

          {/* Restore to original VM */}
          <div className="flex items-center justify-between bg-red-50 border border-red-100 rounded-lg px-4 py-2.5">
            <div className="text-xs text-red-700">
              <strong>Restore to Original VM</strong>
              <div className="text-red-500 mt-0.5">Stops &amp; deletes the original VM after restore completes.</div>
            </div>
            <button
              type="button"
              onClick={() => setRestoreOriginal(v => !v)}
              className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ml-4 ${restoreOriginal ? 'bg-red-500' : 'bg-slate-200'}`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${restoreOriginal ? 'left-5' : 'left-0.5'}`} />
            </button>
          </div>

          {/* Instant recovery info */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 text-xs text-amber-700 flex gap-2">
            <span className="shrink-0">⚡</span>
            <span><strong>Instant Restore</strong> boots from Glance image directly (ephemeral disk) — VM accessible in ~1–2 min. <strong>Full Restore</strong> copies image to a Cinder volume first — takes longer but disk is persistent.</span>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="border border-slate-200 rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!!loading || !flavorId}
              onClick={e => handleSubmit(e, true)}
              className="flex-1 bg-amber-500 hover:bg-amber-400 disabled:opacity-60 text-white font-semibold rounded-lg py-2 text-sm transition-colors flex items-center justify-center gap-1.5"
            >
              {loading === 'instant' && <span className="inline-block w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
              {loading === 'instant' ? 'Starting…' : '⚡ Instant'}
            </button>
            <button
              type="submit"
              disabled={!!loading || !flavorId}
              className="flex-1 bg-sky-500 hover:bg-sky-400 disabled:opacity-60 text-white font-semibold rounded-lg py-2 text-sm transition-colors flex items-center justify-center gap-1.5"
            >
              {loading === 'full' && <span className="inline-block w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
              {loading === 'full' ? 'Starting…' : '↩ Full Restore'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
