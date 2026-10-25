import { useEffect, useState } from 'react'
import { api, ApiError, fmtNum, type Health, type Tenant, type UsageRow } from '../api'

type Page = 'overview' | 'tenants' | 'usage' | 'playground'

interface Props {
  health: Health | null
  onRefresh: () => void
  onGo: (p: Page) => void
}

export default function Overview({ health, onRefresh, onGo }: Props) {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [usage, setUsage] = useState<UsageRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [t, u] = await Promise.all([
        api.get<Tenant[]>('/admin/tenants'),
        api.get<UsageRow[]>('/admin/usage'),
      ])
      setTenants(t)
      setUsage(u)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load gateway stats')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const totalTokens = usage.reduce((s, r) => s + r.total_tokens, 0)
  const totalRequests = usage.reduce((s, r) => s + r.requests, 0)
  const totalKeys = tenants.reduce((s, t) => s + t.active_keys, 0)

  return (
    <>
      <div className="page-head">
        <h2>Gateway at a glance</h2>
        <p>Health, tenants and token traffic across all upstream providers.</p>
      </div>

      {error && (
        <div className="banner err">
          {error} — use “Set admin key” in the top bar to authenticate.
        </div>
      )}

      <div className="grid grid-4">
        <div className="card">
          <div className="stat-label">Status</div>
          <div className={`stat-value ${health?.status === 'ok' ? 'ok' : 'err'}`}>
            {health ? health.status : 'offline'}
          </div>
          <div className="stat-sub">
            env {health?.env ?? '—'} · db {health?.db ? 'connected' : '—'}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Tenants</div>
          <div className="stat-value">{loading ? '…' : tenants.length}</div>
          <div className="stat-sub">{loading ? '' : `${totalKeys} active API keys`}</div>
        </div>
        <div className="card">
          <div className="stat-label">Total tokens</div>
          <div className="stat-value">{loading ? '…' : fmtNum(totalTokens)}</div>
          <div className="stat-sub">prompt + completion</div>
        </div>
        <div className="card">
          <div className="stat-label">Requests</div>
          <div className="stat-value">{loading ? '…' : fmtNum(totalRequests)}</div>
          <div className="stat-sub">recorded usage entries</div>
        </div>
      </div>

      <div className="grid grid-2 mt-16">
        <div className="card">
          <div className="card-title">
            Quick start
            <span className="right">
              <button className="btn btn-ghost btn-sm" onClick={onRefresh}>
                Refresh
              </button>
            </span>
          </div>
          <p className="muted" style={{ marginTop: 0 }}>
            Send an OpenAI-compatible chat request through the gateway with any
            tenant API key:
          </p>
          <pre className="code">{`curl http://localhost:8080/v1/chat/completions \\
  -H "Authorization: Bearer tg_..." \\
  -H "Content-Type: application/json" \\
  -d '{"model":"deepseek-chat",
       "messages":[{"role":"user","content":"hi"}]}'`}</pre>
          <div className="row mt-16">
            <button className="btn btn-primary" onClick={() => onGo('playground')}>
              Open playground
            </button>
            <button className="btn btn-ghost" onClick={() => onGo('tenants')}>
              Create an API key
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Top tenants by tokens</div>
          {usage.length === 0 ? (
            <div className="empty">
              {loading ? 'Loading…' : 'No usage recorded yet — send your first request.'}
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th className="num">Requests</th>
                  <th className="num">Tokens</th>
                  <th>Share</th>
                </tr>
              </thead>
              <tbody>
                {usage
                  .slice()
                  .sort((a, b) => b.total_tokens - a.total_tokens)
                  .slice(0, 5)
                  .map((r) => {
                    const share = totalTokens ? (r.total_tokens / totalTokens) * 100 : 0
                    return (
                      <tr key={r.tenant_id}>
                        <td className="mono">{r.tenant_id}</td>
                        <td className="num">{fmtNum(r.requests)}</td>
                        <td className="num">{fmtNum(r.total_tokens)}</td>
                        <td>
                          <div className="row">
                            <div className="bar-track" style={{ flex: 1 }}>
                              <div className="bar-fill" style={{ width: `${share}%` }} />
                            </div>
                            <span className="muted" style={{ fontSize: 12 }}>
                              {share.toFixed(0)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card mt-16">
        <div className="card-title">Interfaces</div>
        <div className="row">
          <a className="btn btn-ghost btn-sm" href="/docs" target="_blank" rel="noreferrer">
            Swagger /docs
          </a>
          <a className="btn btn-ghost btn-sm" href="/metrics" target="_blank" rel="noreferrer">
            Prometheus /metrics
          </a>
          <a className="btn btn-ghost btn-sm" href="/health" target="_blank" rel="noreferrer">
            /health
          </a>
          <span className="badge accent">OpenAI-compatible</span>
          <span className="badge">SSE streaming</span>
          <span className="badge">PII masking</span>
          <span className="badge">RPM / TPM limits</span>
        </div>
      </div>
    </>
  )
}
