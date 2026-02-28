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
    <div className="card grid-full animate-slide-up" style={{ animationDelay: '0.25s' }}>
      <div className="card-title">
        <span className="icon">&#x1F4DC;</span> Sync History
      </div>

      {items.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px' }}>
          No sync runs yet
        </div>
      ) : (
        <>
          <div className="table-wrapper">
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
                    <tr key={run.id} className={`animate-slide-up stagger-${Math.min(i + 1, 5)}`}>
                      <td>{run.id}</td>
                      <td style={{ fontSize: '13px' }}>
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
          <div className="pagination">
            <span className="pagination-info">
              {offset + 1}\u2013{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="pagination-buttons">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                \u2190 Prev
              </button>
              <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next \u2192
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
