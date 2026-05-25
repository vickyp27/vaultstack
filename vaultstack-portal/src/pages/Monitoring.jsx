import { useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from 'recharts'
import { api } from '../api'
import { formatDate } from '../utils'

function StatBox({ label, value, sub, color = 'slate' }) {
  const colors = {
    green:  'bg-emerald-50 border-emerald-100 text-emerald-700',
    red:    'bg-red-50 border-red-100 text-red-600',
    blue:   'bg-sky-50 border-sky-100 text-sky-700',
    slate:  'bg-slate-50 border-slate-100 text-slate-700',
  }
  return (
    <div className={`rounded-xl border p-5 ${colors[color]}`}>
      <div className="text-xs font-semibold uppercase tracking-wide opacity-70 mb-1">{label}</div>
      <div className="text-3xl font-bold">{value ?? '—'}</div>
      {sub && <div className="text-xs mt-1 opacity-60">{sub}</div>}
    </div>
  )
}

export default function Monitoring() {
  const [health,      setHealth]      = useState(null)
  const [cfg,         setCfg]         = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [saving,      setSaving]      = useState(false)
  const [testing,     setTesting]     = useState(false)
  const [saveMsg,     setSaveMsg]     = useState('')
  const [testResults, setTestResults] = useState(null)
  const [tab,         setTab]         = useState('overview')  // overview | alerts | logs

  useEffect(() => {
    Promise.all([api.monitoringHealth(), api.alertConfig()])
      .then(([h, c]) => { setHealth(h); setCfg(c) })
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true); setSaveMsg('')
    try {
      await api.saveAlertConfig(cfg)
      setSaveMsg('Saved successfully.')
    } catch (err) {
      setSaveMsg('Error: ' + err.message)
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(''), 3000)
    }
  }

  async function handleTest() {
    setTesting(true); setTestResults(null)
    try {
      const res = await api.testAlert()
      setTestResults(res.results)
    } catch (err) {
      setTestResults([{ channel: '—', success: false, error: err.message }])
    } finally {
      setTesting(false)
    }
  }

  if (loading) return (
    <div className="flex-1 flex items-center justify-center py-20 text-slate-300">
      <span className="spin inline-block text-3xl">⟳</span>
    </div>
  )

  const { summary = {}, daily = [], recent_failures = [], alert_logs = [] } = health ?? {}

  return (
    <div className="p-6 space-y-6">

      {/* Tab bar */}
      <div className="flex gap-1 bg-white border border-slate-100 rounded-xl p-1 w-fit shadow-sm">
        {[['overview', 'Overview'], ['alerts', 'Alert Config'], ['logs', 'Alert Logs']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              tab === id ? 'bg-sky-500 text-white' : 'text-slate-500 hover:bg-slate-50'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* ── OVERVIEW TAB ── */}
      {tab === 'overview' && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatBox label="Success rate 24h"
              value={summary.success_rate_24h != null ? `${summary.success_rate_24h}%` : 'N/A'}
              color={summary.success_rate_24h >= 90 ? 'green' : summary.success_rate_24h >= 70 ? 'slate' : 'red'} />
            <StatBox label="Success rate 7d"
              value={summary.success_rate_7d != null ? `${summary.success_rate_7d}%` : 'N/A'}
              color={summary.success_rate_7d >= 90 ? 'green' : summary.success_rate_7d >= 70 ? 'slate' : 'red'} />
            <StatBox label="Jobs (24h)"   value={summary.total_jobs_24h}  color="blue" />
            <StatBox label="Jobs (7d)"    value={summary.total_jobs_7d}   color="blue" />
            <StatBox label="Failed (24h)" value={summary.failed_24h}      color={summary.failed_24h > 0 ? 'red' : 'green'} />
            <StatBox label="Failed (7d)"  value={summary.failed_7d}       color={summary.failed_7d > 0 ? 'red' : 'green'} />
          </div>

          {/* 7-day chart */}
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <div className="text-sm font-semibold text-slate-700 mb-4">7-Day Backup Trend</div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={daily} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
                <Legend />
                <Bar dataKey="success" name="Success" fill="#34d399" radius={[3,3,0,0]} />
                <Bar dataKey="failed"  name="Failed"  fill="#f87171" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Recent failures */}
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
              <span className="text-sm font-semibold text-slate-700">Recent Failures</span>
              <span className="text-xs text-slate-400">{recent_failures.length} jobs</span>
            </div>
            {recent_failures.length === 0 ? (
              <div className="text-center py-10 text-slate-300 text-sm">No failed backups. All good!</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-50">
                    {['VM', 'Error', 'Time'].map(h => (
                      <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-5 py-2.5">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {recent_failures.map(f => (
                    <tr key={f.id} className="hover:bg-red-50/30">
                      <td className="px-5 py-3 font-medium text-slate-800">{f.vm_name ?? '—'}</td>
                      <td className="px-5 py-3 text-red-500 text-xs max-w-xs truncate">{f.error_msg ?? '—'}</td>
                      <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(f.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* ── ALERT CONFIG TAB ── */}
      {tab === 'alerts' && cfg && (
        <form onSubmit={handleSave} className="space-y-5 max-w-2xl">

          {/* Email section */}
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-lg">📧</span>
              <span className="font-semibold text-slate-700">Email Alerts</span>
              <label className="ml-auto flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={cfg.email_enabled}
                  onChange={e => setCfg(c => ({ ...c, email_enabled: e.target.checked }))}
                  className="w-4 h-4 accent-sky-500" />
                <span className="text-sm text-slate-600">Enabled</span>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                ['SMTP Host',   'email_smtp_host',  'smtp.gmail.com', 'text'],
                ['SMTP Port',   'email_smtp_port',  '587',            'number'],
                ['Username',    'email_username',   'you@gmail.com',  'text'],
                ['Password',    'email_password',   '••••••••',       'password'],
                ['From',        'email_from',       'alerts@you.com', 'email'],
                ['To (comma)',  'email_to',         'ops@team.com',   'text'],
              ].map(([label, key, ph, type]) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
                  <input type={type} value={cfg[key] ?? ''} placeholder={ph}
                    onChange={e => setCfg(c => ({ ...c, [key]: type === 'number' ? +e.target.value : e.target.value }))}
                    disabled={!cfg.email_enabled}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 disabled:opacity-40" />
                </div>
              ))}
            </div>
          </div>

          {/* Slack section */}
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-lg">💬</span>
              <span className="font-semibold text-slate-700">Slack Alerts</span>
              <label className="ml-auto flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={cfg.slack_enabled}
                  onChange={e => setCfg(c => ({ ...c, slack_enabled: e.target.checked }))}
                  className="w-4 h-4 accent-sky-500" />
                <span className="text-sm text-slate-600">Enabled</span>
              </label>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Webhook URL</label>
              <input type="url" value={cfg.slack_webhook ?? ''} placeholder="https://hooks.slack.com/services/..."
                onChange={e => setCfg(c => ({ ...c, slack_webhook: e.target.value }))}
                disabled={!cfg.slack_enabled}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 disabled:opacity-40" />
            </div>
          </div>

          {/* When to alert */}
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
            <div className="font-semibold text-slate-700 mb-2">When to Alert</div>
            {[
              ['alert_on_failure', 'Alert on backup failure'],
              ['alert_on_success', 'Alert on backup success'],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={cfg[key]}
                  onChange={e => setCfg(c => ({ ...c, [key]: e.target.checked }))}
                  className="w-4 h-4 accent-sky-500" />
                <span className="text-sm text-slate-700">{label}</span>
              </label>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button type="submit" disabled={saving}
              className="px-5 py-2 bg-sky-500 hover:bg-sky-400 text-white rounded-lg text-sm font-semibold disabled:opacity-60 transition-colors">
              {saving ? 'Saving…' : 'Save Config'}
            </button>
            <button type="button" onClick={handleTest} disabled={testing}
              className="px-5 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-sm font-semibold disabled:opacity-60 transition-colors">
              {testing ? 'Sending…' : 'Send Test Alert'}
            </button>
            {saveMsg && <span className={`text-sm ${saveMsg.startsWith('Error') ? 'text-red-500' : 'text-emerald-600'}`}>{saveMsg}</span>}
          </div>

          {testResults && (
            <div className="bg-slate-50 rounded-xl border border-slate-100 p-4 space-y-2">
              {testResults.map((r, i) => (
                <div key={i} className={`flex items-center gap-2 text-sm ${r.success ? 'text-emerald-600' : 'text-red-500'}`}>
                  <span>{r.success ? '✓' : '✕'}</span>
                  <span className="capitalize font-medium">{r.channel}</span>
                  {!r.success && <span className="text-xs opacity-75">— {r.error}</span>}
                </div>
              ))}
            </div>
          )}
        </form>
      )}

      {/* ── ALERT LOGS TAB ── */}
      {tab === 'logs' && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-50">
            <span className="text-sm font-semibold text-slate-700">Alert History</span>
            <span className="text-xs text-slate-400">{alert_logs.length} entries</span>
          </div>
          {alert_logs.length === 0 ? (
            <div className="text-center py-10 text-slate-300 text-sm">No alerts sent yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-50">
                  {['Level', 'Channel', 'Subject', 'Sent', 'Status'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-5 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {alert_logs.map(a => (
                  <tr key={a.id} className="hover:bg-slate-50/60">
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                        a.level === 'error' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-700'
                      }`}>{a.level}</span>
                    </td>
                    <td className="px-5 py-3 text-slate-500 capitalize">{a.channel}</td>
                    <td className="px-5 py-3 text-slate-700 max-w-xs truncate">{a.subject}</td>
                    <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">{formatDate(a.sent_at)}</td>
                    <td className="px-5 py-3">
                      {a.success
                        ? <span className="text-emerald-600 text-xs font-medium">✓ Sent</span>
                        : <span className="text-red-500 text-xs" title={a.error_detail}>✕ Failed</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
