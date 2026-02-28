import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { SyncRun, PaginatedResponse } from '../types'

const PAGE_SIZE = 10

export default function SyncHistory() {
  const [data, setData] = useState<PaginatedResponse<SyncRun> | null>(null)
  const [offset, setOffset] = useState(0)

  const load = useCallback(() => {
    api.getHistory(PAGE_SIZE, offset).then(setData).catch(() => {})
  }, [offset])

  useEffect(() => { load() }, [load])

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="glass-card animate-float-up delay-4">
      <div className="card-header">
        <div className="card-icon">&#x1F4DC;</div>
        <div className="card-title">Sync History</div>
      </div>

      {items.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px' }}>
          No sync runs yet
        </div>
      ) : (
        <>
          <div className="table-wrapper" style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Started</th>
                  <th>Status</th>
                  <th>Mode</th>
                  <th>Direction</th>
                  <th>Stats</th>
                </tr>
              </thead>
              <tbody>
                {items.map((run, i) => {
                  let stats: Record<string, number> = {}
                  if (run.stats_json) {
                    try { stats = JSON.parse(run.stats_json) } catch { /* ignore */ }
                  }
                  return (
                    <tr key={run.id} className={`animate-float-up delay-${Math.min(i + 1, 5)}`}>
                      <td style={{ fontWeight: 'bold' }}>{run.id}</td>
                      <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        {new Date(run.started_at).toLocaleString()}
                      </td>
                      <td>
                        <span className={`badge badge-${run.status}`}>{run.status}</span>
                      </td>
                      <td>{run.mode}</td>
                      <td style={{ fontSize: '13px' }}>{run.direction.replace(/_/g, ' \u2192 ')}</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {Object.entries(stats)
                          .filter(([, v]) => v > 0)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(', ') || '\u2014'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {offset + 1}\u2013{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                disabled={offset === 0} 
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', color: 'white', border: 'none', cursor: offset === 0 ? 'not-allowed' : 'pointer', opacity: offset === 0 ? 0.5 : 1 }}
              >
                \u2190 Prev
              </button>
              <button 
                disabled={offset + PAGE_SIZE >= total} 
                onClick={() => setOffset(offset + PAGE_SIZE)}
                style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', color: 'white', border: 'none', cursor: offset + PAGE_SIZE >= total ? 'not-allowed' : 'pointer', opacity: offset + PAGE_SIZE >= total ? 0.5 : 1 }}
              >
                Next \u2192
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
