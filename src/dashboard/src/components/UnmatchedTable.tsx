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
    <div className="glass-card animate-float-up delay-2">
      <div className="card-header">
        <div className="card-icon">&#x26A0;&#xFE0F;</div>
        <div className="card-title">Unmatched Queue</div>
      </div>

      {items.length === 0 ? (
        <div style={{ color: 'var(--accent-spotify)', textAlign: 'center', padding: '32px', fontWeight: 'bold' }}>
          All tracks mapped successfully! 🎉
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
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
                  <tr key={track.id} className={`animate-float-up delay-${Math.min((i % 5) + 1, 5)}`}>
                    <td>
                      <span style={{ 
                        color: track.source_service === 'spotify' ? 'var(--accent-spotify)' : 'var(--accent-yandex)',
                        fontWeight: 'bold',
                        textTransform: 'uppercase',
                        fontSize: '12px'
                      }}>
                        {track.source_service === 'spotify' ? '\u25CF' : '\u25B2'}
                        {' '}{track.source_service}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{track.artist}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{track.title}</td>
                    <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{track.attempts}</td>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {new Date(track.last_attempt_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {offset + 1}{'\u2013'}{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                disabled={offset === 0} 
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', color: 'white', border: 'none', cursor: offset === 0 ? 'not-allowed' : 'pointer', opacity: offset === 0 ? 0.5 : 1 }}
              >
                {'\u2190'} Prev
              </button>
              <button 
                disabled={offset + PAGE_SIZE >= total} 
                onClick={() => setOffset(offset + PAGE_SIZE)}
                style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', color: 'white', border: 'none', cursor: offset + PAGE_SIZE >= total ? 'not-allowed' : 'pointer', opacity: offset + PAGE_SIZE >= total ? 0.5 : 1 }}
              >
                Next {'\u2192'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
