export type Mode = 'official' | 'recommended' | 'extended'

export interface Player {
  id: number
  steam_id: string
  profile_url: string | null
  display_name: string
  avatar_url: string | null
  last_synced_at: string | null
  library_valid: boolean
  last_sync_status: string | null
  last_sync_error: string | null
  game_count: number
}

export interface SyncResult {
  player_id: number
  status: string
  games_count: number | null
  error_code: string | null
  message: string | null
}

export interface Filters {
  mode: Mode
  exclude_drawn: boolean
}

export interface EligibleGame {
  name: string
  steam_app_id: number
  steam_url: string
  header_image_url: string | null
  archipelago_game_id: number
  archipelago_name: string
  archipelago_slug: string
  archipelago_status: string
  archipelago_detail_status: string | null
  source_name: string | null
  mapping_id: number
  mapping_type: string
  mapping_verified: boolean
  owned_by_count: number
  players_count: number
}

export interface CommonGames {
  eligible_games_count: number
  players_count: number
  games: EligibleGame[]
}

export interface DrawResult {
  draw_id: number
  selected_game: EligibleGame
  eligible_games_count: number
  players_count: number
  owners: { id: number; display_name: string }[]
}

export interface PlayerGames {
  players_count: number
  players: Record<string, {
    player: { id: number; display_name: string }
    games_count: number
    games: EligibleGame[]
  }>
}

export interface PerPlayerDrawResult {
  draw_id: number
  player: { id: number; display_name: string }
  eligible_games_count: number
  selected_game: EligibleGame
}

export interface PerPlayerDrawResponse {
  players_count: number
  eligible_games_count: number
  allow_duplicates: boolean
  results: PerPlayerDrawResult[]
}

export interface DrawHistoryItem {
  id: number
  created_at: string
  filters: Record<string, unknown>
  archipelago_name: string
  steam_app_id: number | null
  steam_url: string | null
  players: { id: number; display_name: string }[]
}

export interface ApGame {
  id: number
  name: string
  status: string
  detail_status: string | null
  source_name: string | null
  enabled: boolean
  steam_app_ids: number[]
  has_verified_mapping: boolean
}

export interface Mapping {
  id: number
  archipelago_game_id: number
  steam_app_id: number
  mapping_type: string
  confidence: number
  verified: boolean
  archipelago_game_name: string | null
  steam_game_name: string | null
}

export interface Source {
  id: number
  name: string
  url: string
  trust_level: string
  last_synced_at: string | null
  last_sync_status: string | null
  last_error: string | null
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export interface AdminSession {
  authenticated: boolean
  username: string
  default_credentials: boolean
  token: string | null
  expires_at: number | null
}

const TOKEN_KEY = 'admin_token'
export const UNAUTHORIZED_EVENT = 'admin-unauthorized'

export const getToken = () => sessionStorage.getItem(TOKEN_KEY)
export const setToken = (token: string | null) =>
  token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY)

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers.Authorization = 'Bearer ' + token
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && path !== '/admin/login' && path !== '/admin/password') {
      setToken(null)
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    throw new ApiError(res.status, data.error ?? 'ERROR', data.message ?? `Erreur ${res.status}`)
  }
  return data as T
}

export const api = {
  players: () => request<Player[]>('GET', '/players'),
  addPlayer: (input: string) => request<Player>('POST', '/players', { input }),
  deletePlayer: (id: number) => request<void>('DELETE', `/players/${id}`),
  syncPlayer: (id: number) => request<SyncResult>('POST', `/players/${id}/sync?force=true`),
  syncAll: () => request<SyncResult[]>('POST', '/players/sync?force=true'),
  commonGames: (player_ids: number[], filters: Filters) =>
    request<CommonGames>('POST', '/selection/common-games', { player_ids, filters }),
  playerGames: (player_ids: number[], filters: Filters) =>
    request<PlayerGames>('POST', '/selection/player-games', { player_ids, filters }),
  draw: (player_ids: number[], filters: Filters) => request<DrawResult>('POST', '/draw', { player_ids, filters }),
  drawPerPlayer: (player_ids: number[], filters: Filters) =>
    request<PerPlayerDrawResponse>('POST', '/draw/per-player', { player_ids, filters }),
  draws: () => request<DrawHistoryItem[]>('GET', '/draws'),
  clearDraws: () => request<{ deleted: number }>('DELETE', '/draws'),
  login: (username: string, password: string) =>
    request<AdminSession>('POST', '/admin/login', { username, password }),
  logout: () => request<void>('POST', '/admin/logout'),
  session: () => request<AdminSession>('GET', '/admin/session'),
  changePassword: (current_password: string, new_password: string, confirm_password: string, new_username?: string) =>
    request<AdminSession>('POST', '/admin/password', {
      current_password,
      new_password,
      confirm_password,
      new_username: new_username || null,
    }),
  apGames: () => request<ApGame[]>('GET', '/archipelago/games'),
  setGameEnabled: (id: number, enabled: boolean) => request<ApGame>('PATCH', `/archipelago/games/${id}`, { enabled }),
  sources: () => request<Source[]>('GET', '/archipelago/sources'),
  syncArchipelago: () => request<{ source: string; status: string; games_count: number; error: string | null }[]>('POST', '/archipelago/sync'),
  mappings: () => request<Mapping[]>('GET', '/mappings'),
  createMapping: (archipelago_game_id: number, steam_app_id: number) =>
    request<Mapping>('POST', '/mappings', { archipelago_game_id, steam_app_id }),
  updateMapping: (id: number, patch: Partial<Pick<Mapping, 'steam_app_id' | 'verified'>>) =>
    request<Mapping>('PUT', `/mappings/${id}`, patch),
  deleteMapping: (id: number) => request<void>('DELETE', `/mappings/${id}`),
  autoMatch: () => request<{ created: number }>('POST', '/mappings/auto-match'),
}

export const MAX_PLAYERS = 8
