import { useState, useEffect, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'
import { api } from './api'
import type { StatusData } from './types'
import StatusCard from './components/StatusCard'
import StatsBar from './components/StatsBar'
import Controls from './components/Controls'
import SyncHistory from './components/SyncHistory'
import TrackTable from './components/TrackTable'
import UnmatchedTable from './components/UnmatchedTable'
import ConfigPanel from './components/ConfigPanel'
import AnimatedBackground from './components/AnimatedBackground'

type Tab = 'overview' | 'tracks' | 'unmatched' | 'config'

export default function App() {
  const { status: wsStatus, connected } = useWebSocket()
  const [status, setStatus] = useState<StatusData | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  useEffect(() => {
    if (wsStatus) setStatus(wsStatus)
  }, [wsStatus])

  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => {})
  }, [])

  const refresh = useCallback(() => {
    api.getStatus().then(setStatus).catch(() => {})
  }, [])

  return (
    <>
      <AnimatedBackground />
      <div className="app-container">
        <header className="app-header animate-float-up delay-1">
          <div className="brand">
            <div className="brand-icon">&#9835;</div>
            <h1 className="app-title">SPONDEX</h1>
          </div>
          <div className="status-pill">
            <div className={`status-dot ${connected ? 'connected' : ''}`} />
            {connected ? 'LIVE CONNECTION' : 'RECONNECTING...'}
          </div>
        </header>

        <div className="main-content">
          <nav className="nav-sidebar animate-float-up delay-2">
            {(['overview', 'tracks', 'unmatched', 'config'] as Tab[]).map((tab) => (
              <button
                key={tab}
                className={`nav-item ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'overview' && <><span className="nav-icon">&#x1F4CA;</span> Dashboard</>}
                {tab === 'tracks' && <><span className="nav-icon">&#x1F3B5;</span> Tracks</>}
                {tab === 'unmatched' && <><span className="nav-icon">&#x26A0;&#xFE0F;</span> Unmatched</>}
                {tab === 'config' && <><span className="nav-icon">&#x2699;&#xFE0F;</span> Config</>}
              </button>
            ))}
          </nav>

          <main className="animate-float-up delay-3">
            {activeTab === 'overview' && (
              <>
                <StatsBar status={status} />
                <div className="dashboard-grid" style={{ marginTop: '32px' }}>
                  <StatusCard status={status} />
                  <Controls status={status} onAction={refresh} />
                  <div className="grid-full">
                    <SyncHistory />
                  </div>
                </div>
              </>
            )}

            {activeTab === 'tracks' && <TrackTable />}
            {activeTab === 'unmatched' && <UnmatchedTable />}
            {activeTab === 'config' && <ConfigPanel />}
          </main>
        </div>
      </div>
    </>
  )
}
