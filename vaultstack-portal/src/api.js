import { getToken, logout } from './auth'

const BASE = import.meta.env.VITE_API_URL ?? ''

async function get(path) {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (res.status === 401) { logout(); return }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function del(path) {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (res.status === 401) { logout(); return }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function put(path, body = {}) {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (res.status === 401) { logout(); return }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function post(path, body = {}) {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (res.status === 401) { logout(); return }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  stats:             () => get('/api/v1/dashboard/stats'),
  backups:           () => get('/api/v1/backups/'),
  restores:          () => get('/api/v1/restores/'),
  policies:          () => get('/api/v1/policies/'),
  workloads:         () => get('/api/v1/workloads/'),
  vms:               () => get('/api/v1/backups/vms/list'),
  flavors:           (providerId) => get(`/api/v1/restores/flavors${providerId ? `?provider_id=${providerId}` : ''}`),
  networks:          (projectId, providerId) => {
    const params = new URLSearchParams()
    if (projectId)  params.set('project_id',  projectId)
    if (providerId) params.set('provider_id', providerId)
    const qs = params.toString()
    return get(`/api/v1/restores/networks${qs ? `?${qs}` : ''}`)
  },
  createRestore:     (body) => post('/api/v1/restores/', body),
  deleteBackup:      (id) => del(`/api/v1/backups/${id}`),
  bulkDeleteBackups: (ids) => post('/api/v1/backups/bulk-delete', { ids }),
  createPolicy:      (body) => post('/api/v1/policies/', body),
  updatePolicy:      (id, body) => put(`/api/v1/policies/${id}`, body),
  deletePolicy:      (id) => del(`/api/v1/policies/${id}`),
  monitoringHealth:  () => get('/api/v1/monitoring/health'),
  alertConfig:       () => get('/api/v1/monitoring/alert-config'),
  saveAlertConfig:   (body) => put('/api/v1/monitoring/alert-config', body),
  testAlert:         () => post('/api/v1/monitoring/test-alert'),

  createBackup:      (body) => post('/api/v1/backups/', body),
  tenantStats:       () => get('/api/v1/dashboard/tenant-stats'),

  providers:         () => get('/api/v1/providers/'),
  createProvider:    (body) => post('/api/v1/providers/', body),
  updateProvider:    (id, body) => put(`/api/v1/providers/${id}`, body),
  deleteProvider:    (id) => del(`/api/v1/providers/${id}`),
  testProvider:      (id) => post(`/api/v1/providers/${id}/test`),
  providerWorkloads: (id) => get(`/api/v1/providers/${id}/workloads`),

  tenants:                () => get('/api/v1/settings/tenants/'),
  upsertTenant:           (body) => post('/api/v1/settings/tenants/', body),
  deleteTenant:           (pid) => del(`/api/v1/settings/tenants/${pid}`),
  testTenantConnection:   (pid) => post(`/api/v1/settings/tenants/${pid}/test`),

  lockBackup:   (id, lock_days) => post(`/api/v1/backups/${id}/lock`, { lock_days }),
  unlockBackup: (id) => del(`/api/v1/backups/${id}/lock`),

  auditLogs:        (params) => get(`/api/v1/audit/${params ? `?${new URLSearchParams(params)}` : ''}`),
  slaCompliance:    () => get('/api/v1/sla/compliance'),
  slaSummary:       () => get('/api/v1/sla/summary'),

  runTestRestore:       (policyId) => post(`/api/v1/test-restores/${policyId}/run`),
  testRestoreResults:   (policyId) => get(`/api/v1/test-restores/${policyId}/results`),
  allTestRestoreResults:() => get('/api/v1/test-restores/results/all'),

  browseBackup: (backupId, path) => post(`/api/v1/file-restore/${backupId}/browse`, { path }),

  downloadFiles: async (backupId, paths, vmName) => {
    const token = getToken()
    const res = await fetch(`${BASE}/api/v1/file-restore/${backupId}/download`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ paths }),
    })
    if (res.status === 401) { logout(); return }
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `${res.status} ${res.statusText}`)
    }
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `${(vmName || 'backup').replace(/\s+/g, '_')}_files.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
}
