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
    <div className="glass-card animate-float-up delay-2">
      <div className="card-header">
        <div className="card-icon">&#x2699;&#xFE0F;</div>
        <div className="card-title">System Configuration</div>
      </div>

      {config && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
          <div style={{ background: 'rgba(0,0,0,0.2)', padding: '24px', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <h3 style={{ color: 'var(--accent-3)', marginBottom: '16px', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '1px' }}>Daemon</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Dashboard Port</span>
              <span style={{ fontWeight: 'bold' }}>{config.daemon.dashboard_port}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Log Level</span>
              <span style={{ fontWeight: 'bold', textTransform: 'uppercase' }}>{config.daemon.log_level}</span>
            </div>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.2)', padding: '24px', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <h3 style={{ color: 'var(--accent-1)', marginBottom: '16px', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '1px' }}>Sync Engine</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Interval</span>
              <span style={{ fontWeight: 'bold' }}>{config.sync.interval_minutes} min</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Mode</span>
              <span style={{ fontWeight: 'bold', textTransform: 'uppercase' }}>{config.sync.mode}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Propagate Deletions</span>
              <span style={{ fontWeight: 'bold', color: config.sync.propagate_deletions ? 'var(--accent-spotify)' : 'var(--text-muted)' }}>
                {config.sync.propagate_deletions ? 'YES' : 'NO'}
              </span>
            </div>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.2)', padding: '24px', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <h3 style={{ color: 'var(--accent-yandex)', marginBottom: '16px', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '1px' }}>Services</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Spotify</span>
              <span>
                {config.spotify.configured ? (
                  <span style={{ color: 'var(--accent-spotify)', fontWeight: 'bold' }}>{'\u2713'} CONNECTED</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>NOT CONFIGURED</span>
                )}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Yandex Music</span>
              <span>
                {config.yandex.configured ? (
                  <span style={{ color: 'var(--accent-yandex)', fontWeight: 'bold' }}>{'\u2713'} CONNECTED</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>NOT CONFIGURED</span>
                )}
              </span>
            </div>
          </div>
        </div>
      )}

      {collections.length > 0 && (
        <div style={{ marginTop: '32px' }}>
          <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '18px', fontFamily: '"Space Grotesk", sans-serif' }}>Tracked Playlists</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '16px' }}>
            {collections.map((col) => (
              <div key={col.id} style={{ background: 'rgba(255,255,255,0.05)', padding: '16px', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: col.service === 'spotify' ? 'var(--accent-spotify)' : 'var(--accent-yandex)' }}>
                    {col.service === 'spotify' ? '\u25CF' : '\u25B2'}
                  </span>
                  {col.title}
                </span>
                <span style={{ background: 'rgba(0,0,0,0.3)', padding: '4px 12px', borderRadius: '99px', fontSize: '12px', fontWeight: 'bold' }}>
                  {col.track_count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
