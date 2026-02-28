export interface StatusData {
  uptime_seconds: number
  started_at: string
  sync?: {
    state: string
    last_stats: string | null
  }
  scheduler?: {
    paused: boolean
    interval_minutes: number
    next_run_in_seconds: number | null
    total_runs: number
  }
  counts?: {
    tracks: number
    unmatched: number
    collections: number
    sync_runs: number
  }
}

export interface SyncRun {
  id: number
  started_at: string
  finished_at: string | null
  direction: string
  mode: string
  status: string
  stats_json: string | null
  error_message: string | null
}

export interface TrackMapping {
  id: number
  spotify_id: string | null
  yandex_id: string | null
  artist: string
  title: string
  match_confidence: number
  created_at: string
  updated_at: string
}

export interface UnmatchedTrack {
  id: number
  source_service: string
  source_id: string
  artist: string
  title: string
  attempts: number
  last_attempt_at: string
  created_at: string
}

export interface CollectionInfo {
  id: number
  service: string
  collection_type: string
  title: string
  track_count: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ConfigData {
  daemon: { dashboard_port: number; log_level: string }
  sync: { interval_minutes: number; mode: string; propagate_deletions: boolean }
  spotify: { configured: boolean }
  yandex: { configured: boolean }
}

export interface WsMessage {
  type: string
  data: StatusData
}
