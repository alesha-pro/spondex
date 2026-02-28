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
import ChartPanel from './components/ChartPanel'

type Tab = 'overview' | 'tracks' | 'unmatched' | 'config'

export default function App() {
  const { status: wsStatus, connected } = useWebSocket()
  const [status, setStatus] = useState<StatusData | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  // Use WS status when available, fallback to polling
  useEffect(() => {
    if (wsStatus) setStatus(wsStatus)
  }, [wsStatus])

  // Initial fetch
  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => {})
  }, [])

  const refresh = useCallback(() => {
    api.getStatus().then(setStatus).catch(() => {})
  }, [])

  return (
    <div className="app">
      <header className="app-header animate-slide-up">
        <h1 className="app-title">
          <span>&#9835;</span> Spondex
        </h1>
        <div className="ws-indicator">
          <div className={`ws-dot ${connected ? 'connected' : ''}`} />
          {connected ? 'Live' : 'Reconnecting...'}
        </div>
      </header>

      <div className="tabs animate-slide-up" style={{ animationDelay: '0.05s' }}>
        {(['overview', 'tracks', 'unmatched', 'config'] as Tab[]).map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'overview' && 'Overview'}
            {tab === 'tracks' && 'Tracks'}
            {tab === 'unmatched' && 'Unmatched'}
            {tab === 'config' && 'Config'}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <>
          <div className="grid">
            <StatusCard status={status} />
            <Controls status={status} onAction={refresh} />
          </div>
          <StatsBar status={status} />
          <ChartPanel />
          <SyncHistory />
        </>
      )}

      {activeTab === 'tracks' && <TrackTable />}
      {activeTab === 'unmatched' && <UnmatchedTable />}
      {activeTab === 'config' && <ConfigPanel />}
    </div>
  )
}
