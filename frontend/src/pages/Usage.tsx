import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, fmtDate, fmtNum, type Tenant, type UsageRow } from '../api'

export default function Usage() {
  const [rows, setRows] = useState<UsageRow[]>([])
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [u, t] = await Promise.all([
          api.get<UsageRow[]>('/admin/usage'),
          api.get<Tenant[]>('/admin/tenants'),
        ])
        setRows(u)
        setTenants(t)
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Failed to load usage')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const nameOf = (id: string) => tenants.find((t) => t.id === id)?.name ?? id
  const visible = useMemo(
    () => (filter ? rows.filter((r) => r.tenant_id === filter) : rows),
    [rows, filter]
  )

  const totals = visible.reduce(
    (acc, r) => ({
      requests: acc.requests + r.requests,
      prompt: acc.prompt + r.prompt_tokens,
      completion: acc.completion + r.completion_tokens,
      total: acc.total + r.total_tokens,
    }),
    { requests: 0, prompt: 0, completion: 0, total: 0 }
  )
  const max = Math.max(1, ...visible.map((r) => r.total_tokens))

  return (
    <>
      <div className="page-head">
        <h2>Usage</h2>
        <p>Token consumption per tenant, recorded by the gateway on every call.</p>
      </div>

      {error && <div className="banner err">{error}</div>}

      <div className="grid grid-4">
        <div className="card">
          <div className="stat-label">Requests</div>
          <div className="stat-value">{fmtNum(totals.requests)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Prompt tokens</div>
          <div className="stat-value">{fmtNum(totals.prompt)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Completion tokens</div>
          <div className="stat-value">{fmtNum(totals.completion)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Total tokens</div>
          <div className="stat-value">{fmtNum(totals.total)}</div>
        </div>
      </div>

      <div className="card mt-16">
        <div className="card-title">
          Per-tenant usage
          <span className="right">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              style={{ width: 220 }}
            >
              <option value="">All tenants</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </span>
        </div>

        {visible.length === 0 ? (
          <div className="empty">
            {loading ? 'Loading…' : 'No usage recorded yet.'}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Tenant</th>
                <th className="num">Requests</th>
                <th className="num">Prompt</th>
                <th className="num">Completion</th>
                <th className="num">Total</th>
                <th>Volume</th>
              </tr>
            </thead>
            <tbody>
              {visible
                .slice()
                .sort((a, b) => b.total_tokens - a.total_tokens)
                .map((r) => (
                  <tr key={r.tenant_id}>
                    <td>
                      <strong>{nameOf(r.tenant_id)}</strong>
                      <div className="mono muted" style={{ fontSize: 11 }}>
                        {r.tenant_id}
                      </div>
                    </td>
                    <td className="num">{fmtNum(r.requests)}</td>
                    <td className="num">{fmtNum(r.prompt_tokens)}</td>
                    <td className="num">{fmtNum(r.completion_tokens)}</td>
                    <td className="num">
                      <strong>{fmtNum(r.total_tokens)}</strong>
                    </td>
                    <td style={{ minWidth: 140 }}>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${(r.total_tokens / max) * 100}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
        {!loading && rows.length > 0 && (
          <div className="muted mt-8" style={{ fontSize: 12 }}>
            {visible.length} tenant{visible.length === 1 ? '' : 's'} · updated{' '}
            {fmtDate(new Date().toISOString())}
          </div>
        )}
      </div>
    </>
  )
}
