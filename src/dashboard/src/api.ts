import type { StatusData, SyncRun, TrackMapping, UnmatchedTrack, CollectionInfo, PaginatedResponse, ConfigData } from './types'

const BASE = '/api'

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const api = {
  getStatus: () => fetchJson<StatusData>('/status'),
  getHistory: (limit = 20, offset = 0) =>
    fetchJson<PaginatedResponse<SyncRun>>(`/history?limit=${limit}&offset=${offset}`),
  getTracks: (limit = 50, offset = 0, search = '') =>
    fetchJson<PaginatedResponse<TrackMapping>>(`/tracks?limit=${limit}&offset=${offset}&search=${encodeURIComponent(search)}`),
  getUnmatched: (limit = 50, offset = 0) =>
    fetchJson<PaginatedResponse<UnmatchedTrack>>(`/unmatched?limit=${limit}&offset=${offset}`),
  getCollections: () => fetchJson<CollectionInfo[]>('/collections'),
  getConfig: () => fetchJson<ConfigData>('/config'),
  getConfidenceChart: () => fetchJson<{ bucket: string; count: number }[]>('/charts/confidence'),
  getActivityChart: (limit = 12) =>
    fetchJson<{ id: number; started_at: string; mode: string; sp_added: number; ym_added: number; cross_matched: number; unmatched: number }[]>(`/charts/activity?limit=${limit}`),
  triggerSync: (mode: string = 'full') => postJson<{ message: string }>('/sync', { mode }),
  pause: () => postJson<{ message: string }>('/pause'),
  resume: () => postJson<{ message: string }>('/resume'),
}
