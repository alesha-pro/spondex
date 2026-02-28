import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'

interface ConfidenceBucket {
  bucket: string
  count: number
}

interface ActivityPoint {
  id: number
  started_at: string
  mode: string
  sp_added: number
  ym_added: number
  cross_matched: number
  unmatched: number
}

const BUCKET_COLORS: Record<string, string> = {
  exact: '#1db954',
  high: '#4ecdc4',
  medium: '#ffcc00',
  low: '#ef4444',
}

const BUCKET_LABELS: Record<string, string> = {
  exact: '95-100%',
  high: '85-95%',
  medium: '70-85%',
  low: '<70%',
}

// --- Donut Chart -----------------------------------------------------------

function DonutChart({ data }: { data: ConfidenceBucket[] }) {
  const total = data.reduce((s, d) => s + d.count, 0)
  if (total === 0) {
    return (
      <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '32px' }}>
        No track data yet
      </div>
    )
  }

  const radius = 70
  const strokeWidth = 24
  const cx = 100
  const cy = 100
  const circumference = 2 * Math.PI * radius

  let offset = 0
  const segments = data.map((d) => {
    const pct = d.count / total
    const dashArray = `${pct * circumference} ${circumference}`
    const dashOffset = -offset * circumference
    offset += pct
    return { ...d, pct, dashArray, dashOffset }
  })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '24px', justifyContent: 'center' }}>
      <svg width="200" height="200" viewBox="0 0 200 200">
        {segments.map((seg, i) => (
          <circle
            key={seg.bucket}
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={BUCKET_COLORS[seg.bucket] || '#666'}
            strokeWidth={strokeWidth}
            strokeDasharray={seg.dashArray}
            strokeDashoffset={seg.dashOffset}
            strokeLinecap="round"
            transform={`rotate(-90 ${cx} ${cy})`}
            style={{
              transition: 'stroke-dasharray 1s cubic-bezier(0.34, 1.56, 0.64, 1)',
              animationDelay: `${i * 0.15}s`,
            }}
          />
        ))}
        <text
          x={cx}
          y={cy - 8}
          textAnchor="middle"
          fill="var(--text-primary)"
          fontSize="28"
          fontWeight="800"
        >
          {total}
        </text>
        <text
          x={cx}
          y={cy + 14}
          textAnchor="middle"
          fill="var(--text-muted)"
          fontSize="12"
        >
          tracks
        </text>
      </svg>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {segments.map((seg) => (
          <div
            key={seg.bucket}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}
          >
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '4px',
                background: BUCKET_COLORS[seg.bucket] || '#666',
                flexShrink: 0,
              }}
            />
            <span style={{ color: 'var(--text-secondary)', minWidth: '60px' }}>
              {BUCKET_LABELS[seg.bucket] || seg.bucket}
            </span>
            <span style={{ fontWeight: 700 }}>{seg.count}</span>
            <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
              ({(seg.pct * 100).toFixed(0)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// --- Activity Bar Chart ----------------------------------------------------

const BAR_COLORS = {
  cross_matched: '#4ecdc4',
  sp_added: '#1db954',
  ym_added: '#ffcc00',
  unmatched: '#ff6b9d',
}

function ActivityChart({ data }: { data: ActivityPoint[] }) {
  const [animated, setAnimated] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 100)
    return () => clearTimeout(t)
  }, [data])

  if (data.length === 0) {
    return (
      <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '32px' }}>
        No sync runs yet
      </div>
    )
  }

  const maxVal = Math.max(
    ...data.map((d) => d.sp_added + d.ym_added + d.cross_matched + d.unmatched),
    1
  )

  const chartWidth = 500
  const chartHeight = 160
  const padding = { top: 10, right: 10, bottom: 30, left: 10 }
  const innerWidth = chartWidth - padding.left - padding.right
  const innerHeight = chartHeight - padding.top - padding.bottom
  const barWidth = Math.min(32, (innerWidth / data.length) * 0.7)
  const gap = (innerWidth - barWidth * data.length) / (data.length + 1)

  const keys = ['cross_matched', 'sp_added', 'ym_added', 'unmatched'] as const

  return (
    <div>
      <svg
        width="100%"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        style={{ overflow: 'visible' }}
      >
        {/* Grid lines */}
        {[0.25, 0.5, 0.75, 1].map((pct) => (
          <line
            key={pct}
            x1={padding.left}
            x2={chartWidth - padding.right}
            y1={padding.top + innerHeight * (1 - pct)}
            y2={padding.top + innerHeight * (1 - pct)}
            stroke="var(--border-color)"
            strokeDasharray="4 4"
            strokeWidth="0.5"
          />
        ))}

        {/* Bars */}
        {data.map((d, i) => {
          const x = padding.left + gap + i * (barWidth + gap)
          const total = d.sp_added + d.ym_added + d.cross_matched + d.unmatched
          let y = padding.top + innerHeight

          return (
            <g key={d.id}>
              {keys.map((key) => {
                const val = d[key]
                if (val === 0) return null
                const height = animated ? (val / maxVal) * innerHeight : 0
                y -= animated ? height : 0
                return (
                  <rect
                    key={key}
                    x={x}
                    y={y}
                    width={barWidth}
                    height={height}
                    rx={4}
                    fill={BAR_COLORS[key]}
                    opacity={0.9}
                    style={{
                      transition: `all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) ${i * 0.05}s`,
                    }}
                  >
                    <title>{`${key}: ${val}`}</title>
                  </rect>
                )
              })}
              {/* Total label */}
              {total > 0 && animated && (
                <text
                  x={x + barWidth / 2}
                  y={padding.top + innerHeight - (total / maxVal) * innerHeight - 6}
                  textAnchor="middle"
                  fill="var(--text-muted)"
                  fontSize="10"
                  fontWeight="600"
                  style={{
                    transition: `all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) ${i * 0.05 + 0.3}s`,
                  }}
                >
                  {total}
                </text>
              )}
              {/* Run # label */}
              <text
                x={x + barWidth / 2}
                y={chartHeight - 8}
                textAnchor="middle"
                fill="var(--text-muted)"
                fontSize="9"
              >
                #{d.id}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '16px',
          marginTop: '8px',
          flexWrap: 'wrap',
        }}
      >
        {(Object.entries(BAR_COLORS) as [string, string][]).map(([key, color]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
            <div
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '3px',
                background: color,
              }}
            />
            <span style={{ color: 'var(--text-secondary)' }}>
              {key.replace('_', ' ')}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// --- Main Panel ------------------------------------------------------------

export default function ChartPanel() {
  const [confidence, setConfidence] = useState<ConfidenceBucket[]>([])
  const [activity, setActivity] = useState<ActivityPoint[]>([])

  const load = useCallback(() => {
    api.getConfidenceChart().then(setConfidence).catch(() => {})
    api.getActivityChart().then(setActivity).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="grid" style={{ marginBottom: '20px' }}>
      <div className="card animate-slide-up" style={{ animationDelay: '0.15s' }}>
        <div className="card-title">
          <span className="icon">🎯</span> Match Confidence
        </div>
        <DonutChart data={confidence} />
      </div>

      <div className="card animate-slide-up" style={{ animationDelay: '0.2s' }}>
        <div className="card-title">
          <span className="icon">📊</span> Sync Activity
        </div>
        <ActivityChart data={activity} />
      </div>
    </div>
  )
}
