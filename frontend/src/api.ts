// Thin API client for the gateway. Admin routes need the admin key
// (stored locally by the console), playground calls use a tenant API key.

const ADMIN_KEY_STORAGE = 'tg_admin_key'

export function getAdminKey(): string {
  try {
    return localStorage.getItem(ADMIN_KEY_STORAGE) || ''
  } catch {
    return ''
  }
}

export function setAdminKey(key: string) {
  try {
    if (key) localStorage.setItem(ADMIN_KEY_STORAGE, key)
    else localStorage.removeItem(ADMIN_KEY_STORAGE)
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}, admin = true): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (admin) {
    const key = getAdminKey()
    if (key) headers['X-Admin-Key'] = key
  }
  const res = await fetch(path, { ...init, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  get: <T,>(path: string, init: RequestInit = {}, admin = true) =>
    request<T>(path, init, admin),
  post: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  del: <T,>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// ---- types mirroring the gateway API ----

export interface Tenant {
  id: string
  name: string
  is_active: boolean
  created_at: string | null
  active_keys: number
}

export interface ApiKey {
  id: string
  tenant_id: string
  name: string
  prefix: string
  is_active: boolean
  ip_whitelist: string[]
  created_at: string | null
  last_used_at: string | null
}

export interface IssuedKey {
  id: string
  tenant_id: string
  key: string
  prefix: string
}

export interface Quota {
  tenant_id: string
  tenant_name: string
  rpm_limit: number
  tpm_limit: number
  daily_token_cap: number
  monthly_token_cap: number
  daily_tokens_used: number
  monthly_tokens_used: number
}

export interface AuditEntry {
  id: string
  tenant_id: string
  tenant_name: string
  changes: Record<string, { from: number; to: number }>
  created_at: string | null
}

export interface UsageRow {
  tenant_id: string
  requests: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface Health {
  status: string
  env: string
  db: boolean
}

export function fmtNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return String(n)
}

export function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}
