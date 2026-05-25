const KEY = 'vs_token'

export function getToken()            { return localStorage.getItem(KEY) }
export function setToken(t)           { localStorage.setItem(KEY, t) }
export function clearToken()          { localStorage.removeItem(KEY) }
export function isLoggedIn()          { return !!getToken() }

export async function login(username, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Login failed')
  }
  const { token } = await res.json()
  setToken(token)
  return token
}

export function logout() {
  clearToken()
  window.location.href = '/login'
}
