import { useState, useEffect } from 'react'
import { api } from '../api'

const PROVIDER_TYPES = {
  openstack: { label: 'OpenStack', icon: '🌐', color: 'sky',    desc: 'Nova · Cinder · Glance' },
  kubernetes: { label: 'Kubernetes', icon: '⎈', color: 'violet', desc: 'Deployments · PVCs · Pods' },
  vmware:    { label: 'VMware',     icon: '🖥',  color: 'green',  desc: 'vCenter · ESXi (coming soon)' },
  aws:       { label: 'AWS',        icon: '☁️', color: 'orange', desc: 'EC2 · EBS (coming soon)' },
}

const STATUS_STYLES = {
  connected: 'bg-emerald-50 text-emerald-700',
  error:     'bg-red-50 text-red-600',
  unknown:   'bg-slate-100 text-slate-500',
}

const TYPE_BADGE = {
  openstack:  'bg-sky-50 text-sky-700',
  kubernetes: 'bg-violet-50 text-violet-700',
  vmware:     'bg-green-50 text-green-700',
  aws:        'bg-orange-50 text-orange-700',
}

const WORKLOAD_TYPE_BADGE = {
  vm:         'bg-sky-50 text-sky-700',
  deployment: 'bg-violet-50 text-violet-700',
  pvc:        'bg-amber-50 text-amber-700',
}

const EMPTY_FORM = {
  openstack: {
    name: '', endpoint: '',
    credentials: { username: '', password: '', project_name: 'admin', user_domain_name: 'Default', project_domain_name: 'Default' },
  },
  kubernetes: {
    name: '', endpoint: '',
    credentials: { token: '' },
  },
  vmware: { name: '', endpoint: '', credentials: {} },
  aws:    { name: '', endpoint: '', credentials: {} },
}

function blankForm(type) {
  return JSON.parse(JSON.stringify(EMPTY_FORM[type] || { name: '', endpoint: '', credentials: {} }))
}

export default function Infrastructure() {
  const [providers,       setProviders]       = useState([])
  const [loading,         setLoading]         = useState(true)
  const [showModal,       setShowModal]       = useState(false)
  const [editProvider,    setEditProvider]    = useState(null)
  const [step,            setStep]            = useState(1)
  const [selectedType,    setSelectedType]    = useState('')
  const [form,            setForm]            = useState({})
  const [testResult,      setTestResult]      = useState(null)
  const [testing,         setTesting]         = useState(false)
  const [saving,          setSaving]          = useState(false)
  const [saveError,       setSaveError]       = useState('')
  const [workloadsMap,    setWorkloadsMap]    = useState({})
  const [loadingWorkloads, setLoadingWorkloads] = useState(new Set())
  const [expandedMap,     setExpandedMap]     = useState({})

  // Backup Now state
  const [backupModal,     setBackupModal]     = useState({ open: false, vm: null })
  const [policies,        setPolicies]        = useState([])
  const [backupPolicyId,  setBackupPolicyId]  = useState('')
  const [triggering,      setTriggering]      = useState(false)
  const [backupResult,    setBackupResult]    = useState(null)  // { ok, msg, jobId }

  const load = () => {
    setLoading(true)
    api.providers().then(setProviders).catch(() => setProviders([])).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  // ── Backup Now ────────────────────────────────────────────────────────────

  function openBackupModal(vm) {
    setBackupModal({ open: true, vm })
    setBackupPolicyId('')
    setBackupResult(null)
    api.policies().then(setPolicies).catch(() => setPolicies([]))
  }

  function closeBackupModal() {
    setBackupModal({ open: false, vm: null })
    setBackupResult(null)
  }

  async function triggerBackup() {
    if (!backupModal.vm) return
    setTriggering(true)
    setBackupResult(null)
    try {
      const body = { vm_id: backupModal.vm.id }
      if (backupPolicyId) body.policy_id = backupPolicyId
      const res = await api.createBackup(body)
      setBackupResult({ ok: true, msg: `Backup queued — Job ID: ${res.job_id}`, jobId: res.job_id })
    } catch (err) {
      setBackupResult({ ok: false, msg: err.message })
    } finally {
      setTriggering(false)
    }
  }

  // ── Modal open helpers ────────────────────────────────────────────────────

  function openAdd() {
    setEditProvider(null)
    setStep(1)
    setSelectedType('')
    setForm({})
    setTestResult(null)
    setSaveError('')
    setShowModal(true)
  }

  function openEdit(p) {
    setEditProvider(p)
    setSelectedType(p.type)
    // Pre-populate form with existing values; credentials come masked from API
    const f = blankForm(p.type)
    f.name = p.name
    f.endpoint = p.endpoint || ''
    // Copy non-masked creds
    const creds = p.credentials || {}
    Object.keys(f.credentials).forEach(k => {
      f.credentials[k] = creds[k] ?? f.credentials[k]
    })
    setForm(f)
    setTestResult(null)
    setSaveError('')
    setStep(2)
    setShowModal(true)
  }

  function closeModal() {
    setShowModal(false)
    setEditProvider(null)
  }

  // ── Test Connection (in modal) ────────────────────────────────────────────

  async function handleModalTest() {
    setTesting(true)
    setTestResult(null)
    setSaveError('')
    try {
      // First save/create a temp provider to get an ID, then test, then update status
      // For editing: just call test on existing ID
      if (editProvider) {
        // Update first so test uses latest creds
        const body = buildSaveBody()
        await api.updateProvider(editProvider.id, body)
        const res = await api.testProvider(editProvider.id)
        setTestResult({ ok: res.ok, message: res.message })
        load()
      } else {
        // For new providers in add flow, create then test then show result
        const body = buildSaveBody()
        const created = await api.createProvider(body)
        const res = await api.testProvider(created.id)
        setTestResult({ ok: res.ok, message: res.message })
        // Keep the created provider; if user cancels we leave it (user can delete)
        setEditProvider(created)
        load()
      }
    } catch (err) {
      setTestResult({ ok: false, message: err.message })
    } finally {
      setTesting(false)
    }
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  function buildSaveBody() {
    return {
      name: form.name,
      type: selectedType,
      endpoint: form.endpoint || null,
      credentials: form.credentials || {},
    }
  }

  async function handleSave() {
    if (!form.name?.trim()) { setSaveError('Name is required'); return }
    setSaving(true)
    setSaveError('')
    try {
      if (editProvider) {
        await api.updateProvider(editProvider.id, buildSaveBody())
      } else {
        await api.createProvider(buildSaveBody())
      }
      closeModal()
      load()
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  async function handleDelete(p) {
    if (!confirm(`Delete provider "${p.name}"?`)) return
    try {
      await api.deleteProvider(p.id)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  // ── Test (from card) ──────────────────────────────────────────────────────

  const [cardTestResults, setCardTestResults] = useState({})
  const [cardTesting,     setCardTesting]     = useState(null)

  async function handleCardTest(p) {
    setCardTesting(p.id)
    setCardTestResults(r => ({ ...r, [p.id]: null }))
    try {
      const res = await api.testProvider(p.id)
      setCardTestResults(r => ({ ...r, [p.id]: res }))
      load()
    } catch (err) {
      setCardTestResults(r => ({ ...r, [p.id]: { ok: false, message: err.message } }))
    } finally {
      setCardTesting(null)
    }
  }

  // ── Workloads toggle ──────────────────────────────────────────────────────

  async function toggleWorkloads(p) {
    const isExpanded = expandedMap[p.id]
    if (isExpanded) {
      setExpandedMap(m => ({ ...m, [p.id]: false }))
      return
    }
    setExpandedMap(m => ({ ...m, [p.id]: true }))
    if (workloadsMap[p.id]) return  // already loaded
    setLoadingWorkloads(s => new Set([...s, p.id]))
    try {
      const wl = await api.providerWorkloads(p.id)
      setWorkloadsMap(m => ({ ...m, [p.id]: wl }))
    } catch (err) {
      setWorkloadsMap(m => ({ ...m, [p.id]: [] }))
    } finally {
      setLoadingWorkloads(s => { const n = new Set(s); n.delete(p.id); return n })
    }
  }

  // ── Form field helpers ────────────────────────────────────────────────────

  function setField(key, val) {
    setForm(f => ({ ...f, [key]: val }))
  }

  function setCred(key, val) {
    setForm(f => ({ ...f, credentials: { ...f.credentials, [key]: val } }))
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-800">Infrastructure</h2>
          <p className="text-xs text-slate-400 mt-0.5">Manage connected backup sources — OpenStack, Kubernetes, VMware, AWS</p>
        </div>
        <button
          onClick={openAdd}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-sm font-semibold transition-colors"
        >
          + Add Infrastructure
        </button>
      </div>

      {/* Provider grid */}
      {loading ? (
        <div className="text-center py-16 text-slate-300 text-sm">Loading…</div>
      ) : providers.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm text-center py-20 text-slate-300">
          <div className="text-5xl mb-4">⊛</div>
          <p className="text-sm font-medium">No infrastructure providers yet</p>
          <p className="text-xs mt-1">Add an OpenStack, Kubernetes, VMware, or AWS provider to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {providers.map(p => {
            const pt = PROVIDER_TYPES[p.type] || { label: p.type, icon: '⊛', color: 'slate', desc: '' }
            const cardTest = cardTestResults[p.id]
            const wl = workloadsMap[p.id]
            const isExpanded = expandedMap[p.id]
            const isLoadingWl = loadingWorkloads.has(p.id)

            return (
              <div key={p.id} className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
                <div className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    {/* Left: icon + info */}
                    <div className="flex items-start gap-3 min-w-0">
                      <span className="text-2xl flex-shrink-0 mt-0.5">{pt.icon}</span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-slate-800 text-sm">{p.name}</span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${TYPE_BADGE[p.type] || 'bg-slate-100 text-slate-600'}`}>
                            {pt.label}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[p.status] || STATUS_STYLES.unknown}`}>
                            {p.status || 'unknown'}
                          </span>
                        </div>
                        {p.endpoint && (
                          <div className="text-xs text-slate-400 font-mono mt-1 truncate max-w-xs" title={p.endpoint}>
                            {p.endpoint}
                          </div>
                        )}
                        {p.status_msg && (
                          <div className="text-xs text-slate-500 mt-1">{p.status_msg}</div>
                        )}
                        {p.last_tested && (
                          <div className="text-xs text-slate-400 mt-0.5">
                            Last tested: {new Date(p.last_tested).toLocaleString()}
                          </div>
                        )}
                        {isExpanded && wl && (
                          <div className="text-xs text-slate-400 mt-0.5">
                            {wl.length} workload{wl.length !== 1 ? 's' : ''}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right: action icons */}
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => openEdit(p)}
                        title="Edit"
                        className="p-1.5 rounded-lg border border-slate-200 text-slate-400 hover:text-slate-700 hover:bg-slate-50 text-sm transition-colors"
                      >
                        ✎
                      </button>
                      <button
                        onClick={() => handleDelete(p)}
                        title="Delete"
                        className="p-1.5 rounded-lg border border-red-100 text-red-400 hover:text-red-600 hover:bg-red-50 text-sm transition-colors"
                      >
                        🗑
                      </button>
                    </div>
                  </div>

                  {/* Card test result */}
                  {cardTest && (
                    <div className={`mt-3 text-xs px-3 py-1.5 rounded-lg ${cardTest.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                      {cardTest.ok ? '✓' : '✕'} {cardTest.message}
                    </div>
                  )}

                  {/* Card action row */}
                  <div className="flex items-center gap-2 mt-4">
                    <button
                      onClick={() => handleCardTest(p)}
                      disabled={cardTesting === p.id}
                      className="px-3 py-1.5 border border-slate-200 hover:bg-slate-50 text-slate-600 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
                    >
                      {cardTesting === p.id ? 'Testing…' : 'Test Connection'}
                    </button>
                    <button
                      onClick={() => toggleWorkloads(p)}
                      disabled={isLoadingWl}
                      className={`px-3 py-1.5 border rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
                        isExpanded
                          ? 'border-sky-300 bg-sky-50 text-sky-700 hover:bg-sky-100'
                          : 'border-slate-200 hover:bg-slate-50 text-slate-600'
                      }`}
                    >
                      {isLoadingWl ? 'Loading…' : isExpanded ? 'Hide Workloads' : 'View Workloads'}
                    </button>
                  </div>
                </div>

                {/* Workloads table */}
                {isExpanded && (
                  <div className="border-t border-slate-100">
                    {isLoadingWl ? (
                      <div className="text-center py-6 text-slate-300 text-xs">Loading workloads…</div>
                    ) : !wl || wl.length === 0 ? (
                      <div className="text-center py-6 text-slate-300 text-xs">No workloads found</div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="bg-slate-50 border-b border-slate-100">
                              <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Name</th>
                              <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Type</th>
                              <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Status</th>
                              <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Detail</th>
                              <th className="text-left px-4 py-2.5 font-semibold text-slate-500">Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(() => {
                              // Group workloads by project_id (VMs) or namespace (k8s), or "default"
                              const groups = []
                              const groupMap = {}
                              wl.forEach(w => {
                                let groupKey, groupLabel
                                if (w.project_id) {
                                  groupKey   = w.project_id
                                  groupLabel = w.project_name || w.project_id.slice(0, 8)
                                } else if (w.namespace) {
                                  groupKey   = w.namespace
                                  groupLabel = w.namespace
                                } else {
                                  groupKey   = '__default__'
                                  groupLabel = 'Default'
                                }
                                if (!groupMap[groupKey]) {
                                  groupMap[groupKey] = { key: groupKey, label: groupLabel, items: [] }
                                  groups.push(groupMap[groupKey])
                                }
                                groupMap[groupKey].items.push(w)
                              })

                              const rows = []
                              groups.forEach(group => {
                                // Project header row
                                rows.push(
                                  <tr key={`group-${group.key}`} className="bg-slate-50/80 border-b border-slate-100">
                                    <td colSpan={5} className="px-4 py-2">
                                      <div className="flex items-center gap-2">
                                        <span className="text-slate-400">📁</span>
                                        <span className="font-semibold text-slate-700">{group.label}</span>
                                        {group.key !== '__default__' && group.key !== group.label && (
                                          <span className="text-slate-400 font-mono text-[10px]">({group.key.slice(0, 8)}…)</span>
                                        )}
                                        <span className="ml-auto text-slate-400 font-normal">
                                          {group.items.length} {group.items.length === 1 ? 'item' : 'items'}
                                        </span>
                                      </div>
                                    </td>
                                  </tr>
                                )
                                // Items in group
                                group.items.forEach((w, i) => {
                                  rows.push(
                                    <tr key={w.id || `${group.key}-${i}`} className="border-b border-slate-50 hover:bg-slate-50/50">
                                      <td className="px-4 py-2 font-medium text-slate-700 font-mono pl-8">{w.name}</td>
                                      <td className="px-4 py-2">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${WORKLOAD_TYPE_BADGE[w.type] || 'bg-slate-100 text-slate-600'}`}>
                                          {w.type}
                                        </span>
                                      </td>
                                      <td className="px-4 py-2">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                                          /active|running|bound/i.test(w.status)
                                            ? 'bg-emerald-50 text-emerald-700'
                                            : /error|fail|degraded/i.test(w.status)
                                            ? 'bg-red-50 text-red-600'
                                            : 'bg-slate-100 text-slate-500'
                                        }`}>
                                          {w.status}
                                        </span>
                                      </td>
                                      <td className="px-4 py-2 text-slate-400 font-mono">{w.detail}</td>
                                      <td className="px-4 py-2">
                                        {w.type === 'vm' && (
                                          <button
                                            onClick={() => openBackupModal(w)}
                                            className="px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold transition-colors"
                                          >
                                            ↑ Backup Now
                                          </button>
                                        )}
                                      </td>
                                    </tr>
                                  )
                                })
                              })
                              return rows
                            })()}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Backup Now Modal */}
      {backupModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div>
                <h3 className="font-bold text-slate-800">Backup Now</h3>
                <p className="text-xs text-slate-400 mt-0.5 font-mono">{backupModal.vm?.name}</p>
              </div>
              <button onClick={closeBackupModal} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
            </div>

            <div className="px-6 py-5 space-y-4">
              {/* Policy picker */}
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1.5">
                  Assign to Protection Group <span className="text-slate-300">(optional)</span>
                </label>
                <select
                  value={backupPolicyId}
                  onChange={e => setBackupPolicyId(e.target.value)}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
                >
                  <option value="">— Ad-hoc backup (no policy) —</option>
                  {policies.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                <p className="text-xs text-slate-400 mt-1">
                  Ad-hoc backups run immediately without a schedule. Linking to a policy applies its retention rules.
                </p>
              </div>

              {/* Result */}
              {backupResult && (
                <div className={`text-xs px-3 py-2.5 rounded-lg flex items-start gap-2 ${
                  backupResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
                }`}>
                  <span className="font-bold flex-shrink-0">{backupResult.ok ? '✓' : '✕'}</span>
                  <span>{backupResult.msg}</span>
                </div>
              )}

              {/* Actions */}
              {!backupResult?.ok ? (
                <div className="flex gap-3">
                  <button onClick={closeBackupModal}
                    className="flex-1 border border-slate-200 rounded-lg py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
                    Cancel
                  </button>
                  <button onClick={triggerBackup} disabled={triggering}
                    className="flex-1 bg-sky-600 hover:bg-sky-500 disabled:opacity-60 text-white font-semibold rounded-lg py-2 text-sm transition-colors">
                    {triggering ? 'Queuing…' : '↑ Start Backup'}
                  </button>
                </div>
              ) : (
                <button onClick={closeBackupModal}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg py-2 text-sm transition-colors">
                  Done — View in Backup Jobs
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Add / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">

            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-800">
                {editProvider ? `Edit — ${editProvider.name}` : 'Add Infrastructure Provider'}
              </h3>
              <button onClick={closeModal} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
            </div>

            <div className="px-6 py-5 max-h-[80vh] overflow-y-auto space-y-5">

              {/* Step 1: choose type (add mode only) */}
              {!editProvider && step === 1 && (
                <>
                  <p className="text-xs text-slate-500">Select the type of infrastructure to connect:</p>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(PROVIDER_TYPES).map(([key, pt]) => {
                      const comingSoon = key === 'vmware' || key === 'aws'
                      return (
                        <button
                          key={key}
                          onClick={() => {
                            if (comingSoon) return
                            setSelectedType(key)
                            setForm(blankForm(key))
                            setTestResult(null)
                            setStep(2)
                          }}
                          disabled={comingSoon}
                          className={`relative text-left p-4 rounded-xl border-2 transition-all ${
                            comingSoon
                              ? 'border-slate-100 bg-slate-50 opacity-60 cursor-not-allowed'
                              : selectedType === key
                              ? 'border-sky-500 bg-sky-50'
                              : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                          }`}
                        >
                          <div className="text-2xl mb-2">{pt.icon}</div>
                          <div className="font-semibold text-sm text-slate-800">{pt.label}</div>
                          <div className="text-xs text-slate-400 mt-0.5">{pt.desc}</div>
                          {comingSoon && (
                            <div className="absolute inset-0 flex items-center justify-center rounded-xl">
                              <span className="bg-slate-600/80 text-white text-xs font-semibold px-2 py-0.5 rounded-full">Coming soon</span>
                            </div>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </>
              )}

              {/* Step 2: form */}
              {step === 2 && (
                <>
                  {/* Type indicator when adding */}
                  {!editProvider && (
                    <div className="flex items-center gap-2">
                      <button onClick={() => setStep(1)} className="text-xs text-sky-600 hover:underline">← Back</button>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${TYPE_BADGE[selectedType] || 'bg-slate-100 text-slate-600'}`}>
                        {PROVIDER_TYPES[selectedType]?.icon} {PROVIDER_TYPES[selectedType]?.label}
                      </span>
                    </div>
                  )}

                  {selectedType === 'openstack' && (
                    <OpenStackForm form={form} setField={setField} setCred={setCred} />
                  )}

                  {selectedType === 'kubernetes' && (
                    <KubernetesForm form={form} setField={setField} setCred={setCred} />
                  )}

                  {(selectedType === 'vmware' || selectedType === 'aws') && (
                    <div className="text-center py-8 text-slate-400 text-sm">
                      <div className="text-3xl mb-3">{PROVIDER_TYPES[selectedType]?.icon}</div>
                      <p className="font-medium">{PROVIDER_TYPES[selectedType]?.label} support coming soon</p>
                      <p className="text-xs mt-1">This provider type is not yet supported.</p>
                    </div>
                  )}

                  {/* Test result */}
                  {testResult && (
                    <div className={`text-xs px-3 py-2 rounded-lg flex items-start gap-2 ${
                      testResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
                    }`}>
                      <span className="flex-shrink-0 font-bold">{testResult.ok ? '✓' : '✕'}</span>
                      <span>{testResult.message}</span>
                    </div>
                  )}

                  {/* Save error */}
                  {saveError && (
                    <div className="text-xs px-3 py-2 rounded-lg bg-red-50 text-red-600">{saveError}</div>
                  )}

                  {/* Action buttons */}
                  {selectedType !== 'vmware' && selectedType !== 'aws' && (
                    <div className="space-y-2 pt-1">
                      <button
                        type="button"
                        onClick={handleModalTest}
                        disabled={testing || !form.name?.trim()}
                        className="w-full border border-slate-200 hover:bg-slate-50 disabled:opacity-50 text-slate-700 rounded-lg py-2 text-sm font-medium transition-colors"
                      >
                        {testing ? 'Testing connection…' : 'Test Connection'}
                      </button>
                      <div className="flex gap-3">
                        <button
                          type="button"
                          onClick={closeModal}
                          className="flex-1 border border-slate-200 rounded-lg py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={handleSave}
                          disabled={saving || !form.name?.trim()}
                          className="flex-1 bg-sky-600 hover:bg-sky-500 disabled:opacity-60 text-white font-semibold rounded-lg py-2 text-sm transition-colors"
                        >
                          {saving ? 'Saving…' : editProvider ? 'Save Changes' : 'Add Provider'}
                        </button>
                      </div>
                    </div>
                  )}

                  {(selectedType === 'vmware' || selectedType === 'aws') && (
                    <button
                      type="button"
                      onClick={closeModal}
                      className="w-full border border-slate-200 rounded-lg py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                    >
                      Close
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── OpenStack form ────────────────────────────────────────────────────────────

function OpenStackForm({ form, setField, setCred }) {
  const creds = form.credentials || {}
  return (
    <div className="space-y-3">
      <FormField label="Provider Name *" value={form.name} onChange={v => setField('name', v)} placeholder="e.g. Production OpenStack" />
      <FormField label="Auth URL *" value={form.endpoint} onChange={v => setField('endpoint', v)} placeholder="http://keystone:5000/v3" />
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Username" value={creds.username} onChange={v => setCred('username', v)} placeholder="admin" />
        <FormField label="Password" value={creds.password} onChange={v => setCred('password', v)} placeholder="••••••••" type="password" />
        <FormField label="Project Name" value={creds.project_name} onChange={v => setCred('project_name', v)} placeholder="admin" />
        <FormField label="User Domain" value={creds.user_domain_name} onChange={v => setCred('user_domain_name', v)} placeholder="Default" />
        <FormField label="Project Domain" value={creds.project_domain_name} onChange={v => setCred('project_domain_name', v)} placeholder="Default" />
      </div>
    </div>
  )
}

// ── Kubernetes form ───────────────────────────────────────────────────────────

function KubernetesForm({ form, setField, setCred }) {
  const creds = form.credentials || {}
  return (
    <div className="space-y-3">
      <FormField label="Provider Name *" value={form.name} onChange={v => setField('name', v)} placeholder="e.g. Production K8s Cluster" />
      <FormField label="API Server URL *" value={form.endpoint} onChange={v => setField('endpoint', v)} placeholder="https://k8s-api:6443" />
      <FormField label="Bearer Token" value={creds.token} onChange={v => setCred('token', v)} placeholder="eyJhbGciOiJSUzI1NiIs..." type="password" />
    </div>
  )
}

// ── Shared field component ────────────────────────────────────────────────────

function FormField({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <input
        type={type}
        value={value ?? ''}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
      />
    </div>
  )
}
