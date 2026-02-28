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
    if (c >= 0.8) return 'var(--accent-blue)'
    if (c >= 0.6) return 'var(--accent-yandex)'
    return 'var(--accent-red)'
  }

  return (
    <div className="card animate-slide-up">
      <div className="card-title">
        <span className="icon">&#x1F3B5;</span> Track Mappings
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
          <div className="table-wrapper">
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
                  <tr key={track.id} className={`animate-slide-up stagger-${Math.min(i + 1, 5)}`}>
                    <td style={{ fontWeight: 600 }}>{track.artist}</td>
                    <td>{track.title}</td>
                    <td>
                      {track.spotify_id ? (
                        <span className="service-spotify" title={track.spotify_id}>{'\u2713'}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>{'\u2014'}</span>
                      )}
                    </td>
                    <td>
                      {track.yandex_id ? (
                        <span className="service-yandex" title={track.yandex_id}>{'\u2713'}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>{'\u2014'}</span>
                      )}
                    </td>
                    <td>
                      {(track.match_confidence * 100).toFixed(0)}%
                      <div className="confidence-bar">
                        <div
                          className="confidence-fill"
                          style={{
                            width: `${track.match_confidence * 100}%`,
                            background: confidenceColor(track.match_confidence),
                          }}
                        />
                      </div>
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
