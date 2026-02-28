import type { StatusData } from '../types'

interface StatInfo {
  key: string
  label: string
  colorClass: string
}

const STATS: StatInfo[] = [
  { key: 'sp_added', label: 'Sp Added', colorClass: 'spotify' },
  { key: 'ym_added', label: 'Ya Added', colorClass: 'yandex' },
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
    <div className="glass-card animate-pop-in delay-3" style={{ padding: '24px' }}>
      <div className="card-header" style={{ marginBottom: '16px' }}>
        <div className="card-icon">&#x1F4C8;</div>
        <div className="card-title">Live Metrics</div>
      </div>
      <div className="stats-container">
        {STATS.map((s, i) => (
          <div key={s.key} className={`stat-box animate-float-up delay-${(i % 5) + 1}`}>
            <div className={`stat-value ${s.colorClass}`}>
              {stats[s.key] ?? 0}
            </div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
        {counts && (
          <>
            <div className="stat-box animate-float-up delay-5">
              <div className="stat-value">{counts.tracks}</div>
              <div className="stat-label">Total DB</div>
            </div>
            <div className="stat-box animate-float-up delay-5">
              <div className="stat-value">{counts.collections}</div>
              <div className="stat-label">Playlists</div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
