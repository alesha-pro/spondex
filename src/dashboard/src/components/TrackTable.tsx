import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { TrackMapping, PaginatedResponse } from '../types'

const PAGE_SIZE = 25

export default function TrackTable() {
  const [data, setData] = useState<PaginatedResponse<TrackMapping> | null>(null)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [searchDebounced, setSearchDebounced] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      setSearchDebounced(search)
      setOffset(0)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(() => {
    api.getTracks(PAGE_SIZE, offset, searchDebounced).then(setData).catch(() => {})
  }, [offset, searchDebounced])

  useEffect(() => { load() }, [load])

  const items = data?.items ?? []
  const total = data?.total ?? 0

  function confidenceColor(c: number): string {
    if (c >= 0.95) return 'var(--accent-spotify)'
    if (c >= 0.8) return 'var(--accent-3)'
    if (c >= 0.6) return 'var(--accent-yandex)'
    return '#ff4444'
  }

  return (
    <div className="glass-card animate-float-up delay-2">
      <div className="card-header">
        <div className="card-icon">&#x1F3B5;</div>
        <div className="card-title">Track Database</div>
      </div>

      <input
        className="search-input"
        placeholder="Search tracks by artist or title..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {items.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px' }}>
          {searchDebounced ? 'No tracks found' : 'No track mappings yet'}
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Artist</th>
                  <th>Title</th>
                  <th>Spotify</th>
                  <th>Yandex</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {items.map((track, i) => (
                  <tr key={track.id} className={`animate-float-up delay-${Math.min((i % 5) + 1, 5)}`}>
                    <td style={{ fontWeight: 600 }}>{track.artist}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{track.title}</td>
                    <td>
                      {track.spotify_id ? (
                        <span style={{ color: 'var(--accent-spotify)' }} title={track.spotify_id}>{'\u2713'}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>{'\u2014'}</span>
                      )}
                    </td>
                    <td>
                      {track.yandex_id ? (
                        <span style={{ color: 'var(--accent-yandex)' }} title={track.yandex_id}>{'\u2713'}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>{'\u2014'}</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '40px', fontSize: '13px', fontWeight: 'bold' }}>
                          {(track.match_confidence * 100).toFixed(0)}%
                        </span>
                        <div style={{ width: '60px', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div
                            style={{
                              height: '100%',
                              width: `${track.match_confidence * 100}%`,
                              background: confidenceColor(track.match_confidence),
                              transition: 'width 0.5s ease',
                            }}
                          />
                        </div>
                      </div>
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
