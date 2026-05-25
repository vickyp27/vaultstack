export function formatDate(s) {
  if (!s || s === 'None' || s === 'null') return '—'
  try {
    const d = new Date(s.includes('T') || s.includes('Z') ? s : s.replace(' ', 'T') + 'Z')
    return d.toLocaleString()
  } catch {
    return s
  }
}

export function formatSize(gb) {
  if (gb == null) return '—'
  return `${Number(gb).toFixed(2)} GB`
}

export function hasLiveJobs(data) {
  return (
    data.backups.some(j  => ['running', 'queued'].includes(j.status)) ||
    data.restores.some(j => ['running', 'queued'].includes(j.status))
  )
}
