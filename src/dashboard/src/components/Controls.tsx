import { useState } from 'react'
import { api } from '../api'
import type { StatusData } from '../types'

export default function Controls({
  status,
  onAction,
}: {
  status: StatusData | null
  onAction: () => void
}) {
  const [loading, setLoading] = useState<string | null>(null)
  const isPaused = status?.scheduler?.paused ?? false
  const isSyncing = status?.sync?.state === 'syncing'

  const handleSync = async () => {
    setLoading('sync')
    try {
      await api.triggerSync('full')
      onAction()
    } catch { /* ignore */ }
    finally { setLoading(null) }
  }

  const handlePauseResume = async () => {
    setLoading('pause')
    try {
      if (isPaused) {
        await api.resume()
      } else {
        await api.pause()
      }
      onAction()
    } catch { /* ignore */ }
    finally { setLoading(null) }
  }

  return (
    <div className="card animate-slide-up" style={{ animationDelay: '0.15s' }}>
      <div className="card-title">
        <span className="icon">&#x1F3AE;</span> Controls
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <button
          className="btn btn-primary animate-wiggle"
          onClick={handleSync}
          disabled={isSyncing || loading === 'sync'}
        >
          {loading === 'sync' ? (
            <><span className="syncing-indicator" /> Syncing...</>
          ) : isSyncing ? (
            <><span className="syncing-indicator" /> Sync in Progress</>
          ) : (
            'Sync Now'
          )}
        </button>

        <button
          className={`btn ${isPaused ? 'btn-primary' : 'btn-warning'}`}
          onClick={handlePauseResume}
          disabled={loading === 'pause'}
        >
          {isPaused ? 'Resume Scheduler' : 'Pause Scheduler'}
        </button>
      </div>
    </div>
  )
}
