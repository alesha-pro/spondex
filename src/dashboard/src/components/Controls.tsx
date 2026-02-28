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
    <div className="glass-card animate-pop-in delay-5">
      <div className="card-header">
        <div className="card-icon">&#x1F3AE;</div>
        <div className="card-title">Command Center</div>
      </div>

      <div className="controls-list">
        <button
          className="btn-super sync-btn"
          onClick={handleSync}
          disabled={isSyncing || loading === 'sync'}
        >
          {loading === 'sync' || isSyncing ? (
            <><span className="syncing-spinner" /> <span>Syncing...</span></>
          ) : (
            <span>Initiate Full Sync</span>
          )}
        </button>

        <button
          className={`btn-super ${isPaused ? 'resume-btn' : 'pause-btn'}`}
          onClick={handlePauseResume}
          disabled={loading === 'pause'}
        >
          <span>{isPaused ? 'Resume Scheduler' : 'Halt Scheduler'}</span>
        </button>
      </div>
    </div>
  )
}
