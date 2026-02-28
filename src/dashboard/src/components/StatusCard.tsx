import { useMemo } from 'react'
import type { StatusData } from '../types'

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function formatCountdown(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return 'now'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

export default function StatusCard({ status }: { status: StatusData | null }) {
  const syncState = status?.sync?.state ?? 'unknown'
  const badgeClass = `badge badge-${syncState}`

  const uptime = useMemo(
    () => (status ? formatUptime(status.uptime_seconds) : '--'),
    [status]
  )

  const nextRun = status?.scheduler?.next_run_in_seconds

  return (
    <div className="glass-card animate-pop-in delay-4">
      <div className="card-header">
        <div className="card-icon">&#x1F680;</div>
        <div className="card-title">Engine Status</div>
      </div>

      <div className="info-list">
        <div className="info-row">
          <span className="info-label">State</span>
          <span className={badgeClass}>
            {syncState === 'syncing' && <span className="syncing-spinner" />}
            {syncState}
          </span>
        </div>

        <div className="info-row">
          <span className="info-label">Uptime</span>
          <span className="info-val font-display">{uptime}</span>
        </div>

        <div className="info-row">
          <span className="info-label">Scheduler</span>
          <span>
            {status?.scheduler?.paused ? (
              <span className="badge badge-paused">PAUSED</span>
            ) : (
              <span className="badge badge-idle">ACTIVE</span>
            )}
          </span>
        </div>

        {nextRun != null && !status?.scheduler?.paused && (
          <div className="info-row">
            <span className="info-label">Next Sync</span>
            <span className="info-val font-display" style={{ color: 'var(--accent-3)' }}>
              {formatCountdown(nextRun)}
            </span>
          </div>
        )}

        <div className="info-row">
          <span className="info-label">Total Runs</span>
          <span className="info-val font-display">
            {status?.scheduler?.total_runs ?? 0}
          </span>
        </div>
      </div>
    </div>
  )
}
