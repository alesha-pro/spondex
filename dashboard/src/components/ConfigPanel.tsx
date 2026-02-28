import { useState, useEffect } from 'react'
import { api } from '../api'
import type { ConfigData, CollectionInfo } from '../types'

export default function ConfigPanel() {
  const [config, setConfig] = useState<ConfigData | null>(null)
  const [collections, setCollections] = useState<CollectionInfo[]>([])

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => {})
    api.getCollections().then(setCollections).catch(() => {})
  }, [])

  return (
    <div className="card animate-slide-up">
      <div className="card-title">
        <span className="icon">&#x2699;&#xFE0F;</span> Configuration
      </div>

      {config && (
        <>
          <div className="config-section">
            <div className="config-section-title">Daemon</div>
            <div className="config-item">
              <span className="config-key">Dashboard Port</span>
              <span className="config-value">{config.daemon.dashboard_port}</span>
            </div>
            <div className="config-item">
              <span className="config-key">Log Level</span>
              <span className="config-value">{config.daemon.log_level}</span>
            </div>
          </div>

          <div className="config-section">
            <div className="config-section-title">Sync</div>
            <div className="config-item">
              <span className="config-key">Interval</span>
              <span className="config-value">{config.sync.interval_minutes} min</span>
            </div>
            <div className="config-item">
              <span className="config-key">Mode</span>
              <span className="config-value">{config.sync.mode}</span>
            </div>
            <div className="config-item">
              <span className="config-key">Propagate Deletions</span>
              <span className="config-value">{config.sync.propagate_deletions ? 'Yes' : 'No'}</span>
            </div>
          </div>

          <div className="config-section">
            <div className="config-section-title">Services</div>
            <div className="config-item">
              <span className="config-key">Spotify</span>
              <span className="config-value">
                {config.spotify.configured ? (
                  <span style={{ color: 'var(--accent-spotify)' }}>{'\u2713'} Connected</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Not configured</span>
                )}
              </span>
            </div>
            <div className="config-item">
              <span className="config-key">Yandex Music</span>
              <span className="config-value">
                {config.yandex.configured ? (
                  <span style={{ color: 'var(--accent-yandex)' }}>{'\u2713'} Connected</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Not configured</span>
                )}
              </span>
            </div>
          </div>
        </>
      )}

      {collections.length > 0 && (
        <div className="config-section" style={{ marginTop: '20px' }}>
          <div className="config-section-title">Collections</div>
          {collections.map((col) => (
            <div key={col.id} className="config-item">
              <span className="config-key">
                <span className={`service-${col.service}`}>
                  {col.service === 'spotify' ? '\uD83D\uDFE2' : '\uD83D\uDFE1'}
                </span>
                {' '}{col.title}
              </span>
              <span className="config-value">{col.track_count} tracks</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
