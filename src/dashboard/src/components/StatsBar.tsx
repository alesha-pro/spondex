import type { StatusData } from '../types'

interface StatInfo {
  key: string
  label: string
  colorClass: string
}

const STATS: StatInfo[] = [
  { key: 'sp_added', label: 'Spotify Added', colorClass: 'spotify' },
  { key: 'ym_added', label: 'Yandex Added', colorClass: 'yandex' },
  { key: 'cross_matched', label: 'Matched', colorClass: '' },
  { key: 'unmatched', label: 'Unmatched', colorClass: '' },
]

export default function StatsBar({ status }: { status: StatusData | null }) {
  const statsJson = status?.sync?.last_stats
  let stats: Record<string, number> = {}
  if (statsJson) {
    try { stats = JSON.parse(statsJson) } catch { /* ignore */ }
  }

  const counts = status?.counts

  return (
    <div className="card grid-full animate-slide-up" style={{ animationDelay: '0.2s' }}>
      <div className="card-title">
        <span className="icon">&#x1F4C8;</span> Stats
      </div>
      <div className="stats-grid">
        {STATS.map((s, i) => (
          <div key={s.key} className={`stat-item stagger-${i + 1} animate-slide-up`}>
            <div className={`stat-value ${s.colorClass}`}>
              {stats[s.key] ?? 0}
            </div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
        {counts && (
          <>
            <div className="stat-item animate-slide-up stagger-5">
              <div className="stat-value">{counts.tracks}</div>
              <div className="stat-label">Total Tracks</div>
            </div>
            <div className="stat-item animate-slide-up stagger-5">
              <div className="stat-value">{counts.unmatched}</div>
              <div className="stat-label">Unmatched</div>
            </div>
            <div className="stat-item animate-slide-up stagger-5">
              <div className="stat-value">{counts.collections}</div>
              <div className="stat-label">Collections</div>
            </div>
            <div className="stat-item animate-slide-up stagger-5">
              <div className="stat-value">{counts.sync_runs}</div>
              <div className="stat-label">Sync Runs</div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
