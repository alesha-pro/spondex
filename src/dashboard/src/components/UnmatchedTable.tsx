import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { UnmatchedTrack, PaginatedResponse } from '../types'

const PAGE_SIZE = 25

export default function UnmatchedTable() {
  const [data, setData] = useState<PaginatedResponse<UnmatchedTrack> | null>(null)
  const [offset, setOffset] = useState(0)

  const load = useCallback(() => {
    api.getUnmatched(PAGE_SIZE, offset).then(setData).catch(() => {})
  }, [offset])

  useEffect(() => { load() }, [load])

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="card animate-slide-up">
      <div className="card-title">
        <span className="icon">&#x2753;</span> Unmatched Tracks
      </div>

      {items.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px' }}>
          No unmatched tracks {'\u2014'} great!
        </div>
      ) : (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Artist</th>
                  <th>Title</th>
                  <th>Attempts</th>
                  <th>Last Attempt</th>
                </tr>
              </thead>
              <tbody>
                {items.map((track, i) => (
                  <tr key={track.id} className={`animate-slide-up stagger-${Math.min(i + 1, 5)}`}>
                    <td>
                      <span className={`service-${track.source_service}`}>
                        {track.source_service === 'spotify' ? '\uD83D\uDFE2' : '\uD83D\uDFE1'}
                        {' '}{track.source_service}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{track.artist}</td>
                    <td>{track.title}</td>
                    <td style={{ textAlign: 'center' }}>{track.attempts}</td>
                    <td style={{ fontSize: '13px' }}>
                      {new Date(track.last_attempt_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span className="pagination-info">
              {offset + 1}{'\u2013'}{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="pagination-buttons">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                {'\u2190'} Prev
              </button>
              <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next {'\u2192'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
