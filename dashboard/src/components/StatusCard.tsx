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
    <div className="card animate-slide-up" style={{ animationDelay: '0.1s' }}>
      <div className="card-title">
        <span className="icon">&#x1F39B;&#xFE0F;</span> Status
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Engine</span>
          <span className={badgeClass}>
            {syncState === 'syncing' && <span className="syncing-indicator" />}
            {syncState}
          </span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Uptime</span>
          <span style={{ fontWeight: 600 }}>{uptime}</span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Scheduler</span>
          <span style={{ fontWeight: 600 }}>
            {status?.scheduler?.paused ? (
              <span className="badge badge-paused">Paused</span>
            ) : (
              <span className="badge badge-idle">Active</span>
            )}
          </span>
        </div>

        {nextRun != null && !status?.scheduler?.paused && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Next sync</span>
            <span style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>
              {formatCountdown(nextRun)}
            </span>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Total runs</span>
          <span style={{ fontWeight: 600 }}>
            {status?.scheduler?.total_runs ?? 0}
          </span>
        </div>
      </div>
    </div>
  )
}
