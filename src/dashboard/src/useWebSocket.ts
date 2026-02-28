import { useEffect, useRef, useState, useCallback } from 'react'
import type { StatusData, WsMessage } from './types'

export function useWebSocket() {
  const [status, setStatus] = useState<StatusData | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(1000)

  const connect = useCallback(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retryRef.current = 1000
    }

    ws.onmessage = (e) => {
      try {
        const msg: WsMessage = JSON.parse(e.data)
        if (msg.type === 'status') {
          setStatus(msg.data)
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onclose = () => {
      setConnected(false)
      const delay = Math.min(retryRef.current, 30000)
      retryRef.current = delay * 2
      setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    connect()
    return () => { wsRef.current?.close() }
  }, [connect])

  return { status, connected }
}
