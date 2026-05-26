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
  flavors:           () => get('/api/v1/restores/flavors'),
  createRestore:     (body) => post('/api/v1/restores/', body),
  createPolicy:      (body) => post('/api/v1/policies/', body),
  updatePolicy:      (id, body) => put(`/api/v1/policies/${id}`, body),
  deletePolicy:      (id) => del(`/api/v1/policies/${id}`),
  monitoringHealth:  () => get('/api/v1/monitoring/health'),
  alertConfig:       () => get('/api/v1/monitoring/alert-config'),
  saveAlertConfig:   (body) => put('/api/v1/monitoring/alert-config', body),
  testAlert:         () => post('/api/v1/monitoring/test-alert'),

  tenants:                () => get('/api/v1/settings/tenants/'),
  upsertTenant:           (body) => post('/api/v1/settings/tenants/', body),
  deleteTenant:           (pid) => del(`/api/v1/settings/tenants/${pid}`),
  testTenantConnection:   (pid) => post(`/api/v1/settings/tenants/${pid}/test`),
}
