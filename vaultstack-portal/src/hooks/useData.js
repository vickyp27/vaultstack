import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api'

export function useData() {
  const [data, setData]       = useState({ backups: [], restores: [], policies: [], workloads: [], stats: {} })
  const [loading, setLoading] = useState(true)
  const [apiOk, setApiOk]     = useState(null)
  const timerRef              = useRef(null)

  const load = useCallback(async () => {
    try {
      const [backups, restores, policies, workloads, stats] = await Promise.all([
        api.backups(), api.restores(), api.policies(), api.workloads(), api.stats(),
      ])
      setData({ backups, restores, policies, workloads, stats })
      setApiOk(true)
    } catch {
      setApiOk(false)
    } finally {
      setLoading(false)
    }
  }, [])

  // Auto-refresh every 8s when jobs are live
  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    clearTimeout(timerRef.current)
    const hasLive =
      data.backups.some(j  => ['running','queued'].includes(j.status)) ||
      data.restores.some(j => ['running','queued'].includes(j.status))
    if (hasLive) timerRef.current = setTimeout(load, 8000)
    return () => clearTimeout(timerRef.current)
  }, [data, load])

  return { data, loading, apiOk, refresh: load }
}
