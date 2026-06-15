import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function Breadcrumb({ path, onNavigate }) {
  const parts = path.replace(/\/+$/, '').split('/').filter((_, i, a) => i === 0 || a[i] !== '')
  // parts[0] is always "" (root)
  return (
    <nav className="flex items-center gap-1 text-sm flex-wrap">
      <button
        onClick={() => onNavigate('/')}
        className="text-sky-600 hover:text-sky-800 font-medium"
      >
        /
      </button>
      {parts.slice(1).map((part, idx) => {
        const fullPath = '/' + parts.slice(1, idx + 2).join('/')
        const isLast = idx === parts.length - 2
        return (
          <span key={fullPath} className="flex items-center gap-1">
            <span className="text-slate-300">/</span>
            {isLast ? (
              <span className="text-slate-700 font-semibold">{part}</span>
            ) : (
              <button
                onClick={() => onNavigate(fullPath)}
                className="text-sky-600 hover:text-sky-800"
              >
                {part}
              </button>
            )}
          </span>
        )
      })}
    </nav>
  )
}

export default function FileBrowserModal({ backup, onClose }) {
  const [path,        setPath]        = useState('/')
  const [entries,     setEntries]     = useState([])
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState(null)
  const [selected,    setSelected]    = useState(new Set())
  const [downloading, setDownloading] = useState(false)
  const [dlError,     setDlError]     = useState(null)

  const browse = useCallback(async (p) => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.browseBackup(backup.id, p)
      setEntries(data.entries || [])
      setPath(p)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [backup.id])

  useEffect(() => {
    browse('/')
  }, [browse])

  function toggleFile(entry) {
    if (entry.type !== 'file') return
    setSelected(prev => {
      const next = new Set(prev)
      next.has(entry.path) ? next.delete(entry.path) : next.add(entry.path)
      return next
    })
  }

  function toggleAll() {
    const files = entries.filter(e => e.type === 'file').map(e => e.path)
    if (files.every(p => selected.has(p))) {
      setSelected(prev => {
        const next = new Set(prev)
        files.forEach(p => next.delete(p))
        return next
      })
    } else {
      setSelected(prev => {
        const next = new Set(prev)
        files.forEach(p => next.add(p))
        return next
      })
    }
  }

  async function handleDownload() {
    const paths = [...selected]
    if (!paths.length) return
    setDownloading(true)
    setDlError(null)
    try {
      await api.downloadFiles(backup.id, paths, backup.vm_name)
    } catch (e) {
      setDlError(e.message)
    } finally {
      setDownloading(false)
    }
  }

  const files = entries.filter(e => e.type === 'file')
  const allFilesSelected = files.length > 0 && files.every(e => selected.has(e.path))

  if (!backup) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-semibold text-slate-800">File-Level Restore</h2>
            <p className="text-xs text-slate-400 mt-0.5">{backup.vm_name} · {backup.id.substring(0, 8)}…</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
        </div>

        {/* Breadcrumb */}
        <div className="px-6 py-3 bg-slate-50 border-b border-slate-100">
          <Breadcrumb path={path} onNavigate={browse} />
        </div>

        {/* File listing */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400">
              <svg className="animate-spin w-7 h-7 text-sky-500" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
              </svg>
              <span className="text-sm">
                {path === '/' && entries.length === 0
                  ? 'Mounting backup image… this may take 15–30 s on first open'
                  : 'Loading…'}
              </span>
            </div>
          )}
          {!loading && error && (
            <div className="m-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">
              {error}
            </div>
          )}
          {!loading && !error && entries.length === 0 && (
            <div className="py-16 text-center text-slate-300 text-sm">Empty directory</div>
          )}
          {!loading && !error && entries.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-50 sticky top-0 bg-white z-10">
                  <th className="px-4 py-2.5 w-8">
                    <input
                      type="checkbox"
                      checked={allFilesSelected}
                      onChange={toggleAll}
                      disabled={files.length === 0}
                      className="accent-sky-500 cursor-pointer disabled:cursor-default"
                      title="Select all files"
                    />
                  </th>
                  <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 py-2.5">Name</th>
                  <th className="text-right text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 py-2.5 pr-6">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {/* Folders first */}
                {entries.filter(e => e.type === 'dir').map(entry => (
                  <tr key={entry.path} className="hover:bg-slate-50/60">
                    <td className="px-4 py-2.5" />
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => browse(entry.path)}
                        className="flex items-center gap-2 text-slate-700 hover:text-sky-600 font-medium text-left"
                      >
                        <span className="text-base">📁</span>
                        <span>{entry.name}</span>
                      </button>
                    </td>
                    <td className="px-4 py-2.5 pr-6 text-right text-slate-300 text-xs">—</td>
                  </tr>
                ))}
                {/* Files */}
                {entries.filter(e => e.type === 'file').map(entry => (
                  <tr
                    key={entry.path}
                    onClick={() => toggleFile(entry)}
                    className={`cursor-pointer hover:bg-slate-50/60 transition-colors ${
                      selected.has(entry.path) ? 'bg-sky-50/40' : ''
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selected.has(entry.path)}
                        onChange={() => toggleFile(entry)}
                        onClick={e => e.stopPropagation()}
                        className="accent-sky-500 cursor-pointer"
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2 text-slate-600">
                        <span className="text-base">📄</span>
                        <span className="font-mono text-xs">{entry.name}</span>
                      </span>
                    </td>
                    <td className="px-4 py-2.5 pr-6 text-right text-slate-400 text-xs tabular-nums">
                      {formatSize(entry.size)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex items-center justify-between gap-4">
          <div className="text-sm text-slate-500">
            {selected.size > 0
              ? <span className="font-medium text-sky-700">{selected.size} file{selected.size > 1 ? 's' : ''} selected</span>
              : <span className="text-slate-400">Select files to download</span>}
          </div>
          <div className="flex items-center gap-3">
            {dlError && <span className="text-xs text-red-500 max-w-xs truncate">{dlError}</span>}
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 rounded-lg border border-slate-200 hover:bg-white transition-colors"
            >
              Close
            </button>
            <button
              onClick={handleDownload}
              disabled={selected.size === 0 || downloading}
              className="flex items-center gap-2 px-4 py-2 bg-sky-500 hover:bg-sky-600 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {downloading ? (
                <>
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  Extracting…
                </>
              ) : (
                <>⬇ Download {selected.size > 0 ? `(${selected.size})` : ''}</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
