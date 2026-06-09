import { useState, useEffect } from 'react'
import { api } from '../api'

const EMPTY = {
  project_id: '', project_name: '', s3_endpoint_url: '',
  s3_access_key: '', s3_secret_key: '', s3_bucket_name: '',
  s3_region: 'us-east-1', enabled: true,
}

export default function TenantStorage() {
  const [tenants,     setTenants]     = useState([])
  const [form,        setForm]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [saving,      setSaving]      = useState(false)
  const [testing,     setTesting]     = useState(null)
  const [testResult,  setTestResult]  = useState({})
  const [error,       setError]       = useState('')
  const [tenantStats, setTenantStats] = useState([])

  const load = () => {
    api.tenants().then(setTenants).finally(() => setLoading(false))
    api.tenantStats().then(setTenantStats).catch(() => {})
  }
  useEffect(() => { load() }, [])

  async function handleSave(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await api.upsertTenant(form)
      setForm(null)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(pid) {
    if (!confirm(`Delete storage config for project ${pid}?`)) return
    await api.deleteTenant(pid)
    load()
  }

  async function handleTest(pid) {
    setTesting(pid)
    setTestResult(r => ({ ...r, [pid]: null }))
    try {
      const res = await api.testTenantConnection(pid)
      setTestResult(r => ({ ...r, [pid]: res }))
    } catch (err) {
      setTestResult(r => ({ ...r, [pid]: { success: false, message: err.message } }))
    } finally {
      setTesting(null)
    }
  }

  return (
    <div className="p-6 space-y-6">

      {/* Tenant Backup Stats */}
      {tenantStats.length > 0 && (
        <div>
          <h2 className="text-base font-bold text-slate-800 mb-1">Tenant Overview</h2>
          <p className="text-xs text-slate-400 mb-3">Per-project backup activity across all tenants.</p>
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left px-4 py-3 font-semibold text-slate-500">Project ID</th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-500">Policies</th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-500">Total Jobs</th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-500">Success</th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-500">Failed</th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-500">Success Rate</th>
                  <th className="text-right px-4 py-3 font-semibold text-slate-500">Storage Used</th>
                  <th className="text-left px-4 py-3 font-semibold text-slate-500">Last Backup</th>
                </tr>
              </thead>
              <tbody>
                {tenantStats.map(t => (
                  <tr key={t.project_id} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="px-4 py-2.5 font-mono text-slate-700">
                      <span title={t.project_id}>{t.project_id_short}…</span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-600">{t.policies}</td>
                    <td className="px-4 py-2.5 text-right font-semibold text-slate-700">{t.total_backups}</td>
                    <td className="px-4 py-2.5 text-right text-emerald-600">{t.success_backups}</td>
                    <td className="px-4 py-2.5 text-right text-red-500">{t.failed_backups}</td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={`px-2 py-0.5 rounded-full font-semibold ${
                        t.success_rate >= 90 ? 'bg-emerald-50 text-emerald-700' :
                        t.success_rate >= 70 ? 'bg-amber-50 text-amber-700' :
                        'bg-red-50 text-red-600'
                      }`}>
                        {t.success_rate}%
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-600">{t.storage_gb} GB</td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {t.last_backup_at ? t.last_backup_at.slice(0, 16) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-800">Per-Tenant Storage</h2>
          <p className="text-xs text-slate-400 mt-0.5">Each OpenStack project can have its own S3 bucket. Falls back to global config if not set.</p>
        </div>
        <button onClick={() => setForm({ ...EMPTY })}
          className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-white rounded-lg text-sm font-semibold transition-colors">
          + Add Tenant Config
        </button>
      </div>

      {/* How it works banner */}
      <div className="bg-sky-50 border border-sky-100 rounded-xl px-5 py-3 text-sm text-sky-800 flex gap-3">
        <span className="text-lg flex-shrink-0">ℹ</span>
        <div>
          When a backup runs, VaultStack checks if the VM's project has a custom S3 config here.
          If yes → backups go to <strong>that tenant's bucket</strong>.
          If no → falls back to <strong>global storage config</strong>.
          Backup path includes project prefix: <code className="bg-sky-100 px-1 rounded text-xs">s3://bucket/project-id/vm-id/backup.qcow2</code>
        </div>
      </div>

      {/* Tenant list */}
      {loading ? (
        <div className="text-center py-12 text-slate-300 text-sm">Loading…</div>
      ) : tenants.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm text-center py-16 text-slate-300">
          <div className="text-4xl mb-3">🗄</div>
          <p className="text-sm">No per-tenant configs yet.</p>
          <p className="text-xs mt-1">All projects use the global storage config.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {tenants.map(t => (
            <div key={t.project_id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-slate-800">{t.project_name || t.project_id}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                      t.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    }`}>{t.enabled ? 'Active' : 'Disabled'}</span>
                  </div>
                  <div className="text-xs text-slate-400 font-mono mb-3">{t.project_id}</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-1 text-xs">
                    <div><span className="text-slate-400">Bucket:</span> <span className="font-medium text-slate-700">{t.s3_bucket_name}</span></div>
                    <div><span className="text-slate-400">Region:</span> <span className="font-medium text-slate-700">{t.s3_region}</span></div>
                    <div><span className="text-slate-400">Endpoint:</span> <span className="font-medium text-slate-700">{t.s3_endpoint_url || 'AWS default'}</span></div>
                    <div><span className="text-slate-400">Key:</span> <span className="font-medium text-slate-700">{t.s3_access_key ? '●●●●' : '—'}</span></div>
                  </div>
                  {testResult[t.project_id] && (
                    <div className={`mt-3 text-xs px-3 py-1.5 rounded-lg ${
                      testResult[t.project_id].success
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-red-50 text-red-600'
                    }`}>
                      {testResult[t.project_id].success ? '✓' : '✕'} {testResult[t.project_id].message}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button onClick={() => handleTest(t.project_id)} disabled={testing === t.project_id}
                    className="px-3 py-1.5 border border-slate-200 hover:bg-slate-50 text-slate-600 rounded-lg text-xs font-medium disabled:opacity-50">
                    {testing === t.project_id ? 'Testing…' : 'Test'}
                  </button>
                  <button onClick={() => setForm({ ...t, s3_secret_key: '' })}
                    className="px-3 py-1.5 border border-slate-200 hover:bg-slate-50 text-slate-600 rounded-lg text-xs font-medium">
                    Edit
                  </button>
                  <button onClick={() => handleDelete(t.project_id)}
                    className="px-3 py-1.5 border border-red-200 hover:bg-red-50 text-red-500 rounded-lg text-xs font-medium">
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit modal */}
      {form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-800">{form.project_id && tenants.find(t => t.project_id === form.project_id) ? 'Edit' : 'Add'} Tenant Storage Config</h3>
              <button onClick={() => setForm(null)} className="text-slate-400 hover:text-slate-600 text-xl">&times;</button>
            </div>

            <form onSubmit={handleSave} className="px-6 py-5 space-y-3 max-h-[80vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Project ID',   'project_id',      'xxxxxxxx-xxxx-...', 'text',     true],
                  ['Project Name', 'project_name',    'e.g. production',   'text',     false],
                  ['S3 Bucket',    's3_bucket_name',  'my-tenant-backups', 'text',     true],
                  ['Region',       's3_region',       'us-east-1',         'text',     false],
                  ['Endpoint URL', 's3_endpoint_url', 'https://... (optional)', 'url', false],
                  ['Access Key',   's3_access_key',   'AKIA...',           'text',     false],
                  ['Secret Key',   's3_secret_key',   '••••••••',          'password', false],
                ].map(([label, key, ph, type, req]) => (
                  <div key={key} className={key === 's3_endpoint_url' ? 'col-span-2' : ''}>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{label}{req && ' *'}</label>
                    <input type={type} value={form[key] ?? ''} placeholder={ph} required={req}
                      onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400" />
                  </div>
                ))}
              </div>

              <label className="flex items-center gap-2 cursor-pointer mt-1">
                <input type="checkbox" checked={form.enabled}
                  onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))}
                  className="w-4 h-4 accent-sky-500" />
                <span className="text-sm text-slate-700">Enable this config</span>
              </label>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-red-600 text-sm">{error}</div>
              )}

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setForm(null)}
                  className="flex-1 border border-slate-200 rounded-lg py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Cancel
                </button>
                <button type="submit" disabled={saving}
                  className="flex-1 bg-sky-500 hover:bg-sky-400 disabled:opacity-60 text-white font-semibold rounded-lg py-2 text-sm transition-colors">
                  {saving ? 'Saving…' : 'Save Config'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
