import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Overview   from './pages/Overview'
import BackupJobs from './pages/BackupJobs'
import RestoreJobs from './pages/RestoreJobs'
import Policies   from './pages/Policies'
import Workloads   from './pages/Workloads'
import Monitoring    from './pages/Monitoring'
import TenantStorage from './pages/TenantStorage'
import Login         from './pages/Login'
import { useData } from './hooks/useData'
import { isLoggedIn, logout } from './auth'

const PAGE_TITLES = {
  '/':           ['Overview',           'Summary of all backup activity'],
  '/jobs':       ['Backup Jobs',        'All individual VM backup records'],
  '/restores':   ['Restore Jobs',       'All VM restore operations'],
  '/policies':   ['Protection Groups',  'Scheduled backup policies'],
  '/workloads':  ['Workloads',          'Multi-VM workload snapshots'],
  '/monitoring': ['Monitoring',         'Health, alerts & notification config'],
  '/tenants':    ['Tenant Storage',     'Per-project S3 bucket configuration'],
}

function ProtectedApp() {
  const { data, loading, apiOk, refresh } = useData()
  const { pathname } = useLocation()
  const [title, subtitle] = PAGE_TITLES[pathname] ?? ['VaultStack', '']

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      <Sidebar apiOk={apiOk} />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="bg-white border-b border-slate-100 px-6 py-4 flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-base font-bold text-slate-800">{title}</h1>
            <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={refresh}
              disabled={loading}
              className="flex items-center gap-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg px-3.5 py-2 text-xs font-medium text-slate-600 transition-colors disabled:opacity-50"
            >
              <span className={loading ? 'spin inline-block' : 'inline-block'}>⟳</span>
              Refresh
            </button>
            <button
              onClick={logout}
              className="flex items-center gap-2 bg-slate-50 hover:bg-red-50 border border-slate-200 hover:border-red-200 rounded-lg px-3.5 py-2 text-xs font-medium text-slate-600 hover:text-red-600 transition-colors"
            >
              Sign out
            </button>
          </div>
        </header>

        {/* Loading skeleton */}
        {loading && (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-slate-400">
              <span className="text-3xl spin inline-block">⟳</span>
              <span className="text-sm">Loading data…</span>
            </div>
          </div>
        )}

        {/* Content */}
        {!loading && (
          <main className="flex-1 overflow-y-auto">
            <Routes>
              <Route path="/"          element={<Overview    data={data} />} />
              <Route path="/jobs"      element={<BackupJobs  data={data} onRefresh={refresh} />} />
              <Route path="/restores"  element={<RestoreJobs data={data} />} />
              <Route path="/policies"  element={<Policies    data={data} onRefresh={refresh} />} />
              <Route path="/workloads"  element={<Workloads   data={data} />} />
              <Route path="/monitoring" element={<Monitoring />} />
              <Route path="/tenants"    element={<TenantStorage />} />
              <Route path="*"          element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const { pathname } = useLocation()

  if (!isLoggedIn()) {
    if (pathname !== '/login') return <Navigate to="/login" replace />
    return <Login />
  }

  if (pathname === '/login') return <Navigate to="/" replace />

  return (
    <Routes>
      <Route path="/*" element={<ProtectedApp />} />
    </Routes>
  )
}
