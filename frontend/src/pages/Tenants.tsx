import { useCallback, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  fmtDate,
  fmtNum,
  type ApiKey,
  type AuditEntry,
  type IssuedKey,
  type Quota,
  type Tenant,
} from '../api'

export default function Tenants() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [quotas, setQuotas] = useState<Quota[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [newTenant, setNewTenant] = useState('')
  const [issueFor, setIssueFor] = useState('')
  const [keyName, setKeyName] = useState('default')
  const [ipList, setIpList] = useState('')
  const [issued, setIssued] = useState<IssuedKey | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState<Quota | null>(null)
  const [draft, setDraft] = useState({ rpm: '', tpm: '', daily: '', monthly: '' })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [t, k, q, a] = await Promise.all([
        api.get<Tenant[]>('/admin/tenants'),
        api.get<ApiKey[]>('/admin/api-keys'),
        api.get<Quota[]>('/admin/quotas'),
        api.get<AuditEntry[]>('/admin/audit'),
      ])
      setTenants(t)
      setKeys(k)
      setQuotas(q)
      setAudit(a)
      if (!issueFor && t.length) setIssueFor(t[0].id)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [issueFor])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const createTenant = () =>
    run(async () => {
      if (!newTenant.trim()) return
      await api.post<Tenant>('/admin/tenants', { name: newTenant.trim() })
      setNewTenant('')
      setNotice('Tenant created.')
      await load()
    })

  const issueKey = () =>
    run(async () => {
      if (!issueFor) return
      const body: Record<string, unknown> = { tenant_id: issueFor, name: keyName || 'default' }
      const ips = ipList
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      if (ips.length) body.ip_whitelist = ips
      const res = await api.post<IssuedKey>('/admin/api-keys', body)
      setIssued(res)
      setCopied(false)
      setKeyName('default')
      setIpList('')
      await load()
    })

  const revoke = (id: string) =>
    run(async () => {
      await api.del(`/admin/api-keys/${id}`)
      setNotice('API key revoked.')
      await load()
    })

  const copyKey = async () => {
    if (!issued) return
    try {
      await navigator.clipboard.writeText(issued.key)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  const openEdit = (q: Quota) => {
    setEditing(q)
    setDraft({
      rpm: String(q.rpm_limit),
      tpm: String(q.tpm_limit),
      daily: String(q.daily_token_cap),
      monthly: String(q.monthly_token_cap),
    })
  }

  const saveQuota = () =>
    run(async () => {
      if (!editing) return
      const nums = {
        rpm_limit: Number(draft.rpm),
        tpm_limit: Number(draft.tpm),
        daily_token_cap: Number(draft.daily),
        monthly_token_cap: Number(draft.monthly),
      }
      if (Object.values(nums).some((n) => !Number.isFinite(n) || n < 1)) {
        setError('All quota values must be whole numbers of at least 1.')
        return
      }
      await api.put(`/admin/quotas/${editing.tenant_id}`, nums)
      setEditing(null)
      setNotice('Quota updated — applies to new requests immediately.')
      await load()
    })

  const fmtChanges = (changes: AuditEntry['changes']) =>
    Object.entries(changes)
      .map(([field, v]) => `${field}: ${v.from} → ${v.to}`)
      .join('   ·   ')

  const pct = (used: number, cap: number) =>
    cap > 0 ? Math.min(100, (used / cap) * 100) : 0
  const barColor = (p: number) =>
    p >= 90 ? 'var(--err)' : p >= 75 ? 'var(--warn)' : 'var(--accent)'

  return (
    <>
      <div className="page-head">
        <h2>Tenants & API keys</h2>
        <p>Create tenants, issue scoped keys and revoke them when needed.</p>
      </div>

      {error && <div className="banner err">{error}</div>}
      {notice && <div className="banner ok">{notice}</div>}

      {issued && (
        <div className="banner info">
          <strong>Key issued — copy it now, it is not shown again.</strong>
          <div className="row mt-8">
            <code className="mono" style={{ wordBreak: 'break-all' }}>
              {issued.key}
            </code>
            <button className="btn btn-ghost btn-sm" onClick={copyKey}>
              {copied ? 'Copied ✓' : 'Copy'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setIssued(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">New tenant</div>
          <label className="field">
            <span>Tenant name</span>
            <input
              type="text"
              value={newTenant}
              placeholder="e.g. acme-beijing"
              onChange={(e) => setNewTenant(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createTenant()}
            />
          </label>
          <div className="row end">
            <button
              className="btn btn-primary"
              onClick={createTenant}
              disabled={busy || !newTenant.trim()}
            >
              {busy ? <span className="spin" /> : 'Create tenant'}
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Issue API key</div>
          <div className="form-grid">
            <label className="field">
              <span>Tenant</span>
              <select value={issueFor} onChange={(e) => setIssueFor(e.target.value)}>
                {tenants.length === 0 && <option value="">No tenants yet</option>}
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.id})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Key name</span>
              <input
                type="text"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder="default"
              />
            </label>
          </div>
          <label className="field">
            <span>IP whitelist (optional, comma separated)</span>
            <input
              type="text"
              value={ipList}
              onChange={(e) => setIpList(e.target.value)}
              placeholder="203.0.113.5, 198.51.100.7"
            />
          </label>
          <div className="row end">
            <button
              className="btn btn-primary"
              onClick={issueKey}
              disabled={busy || !issueFor}
            >
              {busy ? <span className="spin" /> : 'Issue key'}
            </button>
          </div>
        </div>
      </div>

      <div className="card mt-16">
        <div className="card-title">
          Tenants
          <span className="right muted" style={{ fontSize: 12 }}>
            {loading ? 'loading…' : `${tenants.length} total`}
          </span>
        </div>
        {tenants.length === 0 ? (
          <div className="empty">{loading ? 'Loading…' : 'No tenants yet — create one above.'}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Tenant ID</th>
                <th className="num">Active keys</th>
                <th>Created</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id}>
                  <td>
                    <strong>{t.name}</strong>
                  </td>
                  <td className="mono">{t.id}</td>
                  <td className="num">{t.active_keys}</td>
                  <td className="muted">{fmtDate(t.created_at)}</td>
                  <td>
                    <span className={`badge ${t.is_active ? 'ok' : ''}`}>
                      <span className="dot" />
                      {t.is_active ? 'active' : 'disabled'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card mt-16">
        <div className="card-title">
          Quota limits
          <span className="right muted" style={{ fontSize: 12 }}>
            enforced at request time
          </span>
        </div>
        {quotas.length === 0 ? (
          <div className="empty">
            {loading ? 'Loading…' : 'No quotas configured yet.'}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Tenant</th>
                <th className="num">RPM</th>
                <th className="num">TPM</th>
                <th>Daily tokens</th>
                <th>Monthly tokens</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {quotas.map((q) => {
                const d = pct(q.daily_tokens_used, q.daily_token_cap)
                const m = pct(q.monthly_tokens_used, q.monthly_token_cap)
                return (
                  <tr key={q.tenant_id}>
                    <td>
                      <strong>{q.tenant_name}</strong>
                      <div className="mono muted" style={{ fontSize: 11 }}>
                        {q.tenant_id}
                      </div>
                    </td>
                    <td className="num">{q.rpm_limit}</td>
                    <td className="num">{fmtNum(q.tpm_limit)}</td>
                    <td style={{ minWidth: 150 }}>
                      <div className="mono" style={{ fontSize: 12 }}>
                        {fmtNum(q.daily_tokens_used)} / {fmtNum(q.daily_token_cap)}
                      </div>
                      <div className="bar-track" style={{ marginTop: 4 }}>
                        <div
                          className="bar-fill"
                          style={{ width: `${d}%`, background: barColor(d) }}
                        />
                      </div>
                    </td>
                    <td style={{ minWidth: 150 }}>
                      <div className="mono" style={{ fontSize: 12 }}>
                        {fmtNum(q.monthly_tokens_used)} / {fmtNum(q.monthly_token_cap)}
                      </div>
                      <div className="bar-track" style={{ marginTop: 4 }}>
                        <div
                          className="bar-fill"
                          style={{ width: `${m}%`, background: barColor(m) }}
                        />
                      </div>
                    </td>
                    <td className="num">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => openEdit(q)}
                        disabled={busy}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card mt-16">
        <div className="card-title">
          Recent quota changes
          <span className="right muted" style={{ fontSize: 12 }}>
            {audit.length} entr{audit.length === 1 ? 'y' : 'ies'}
          </span>
        </div>
        {audit.length === 0 ? (
          <div className="empty">
            {loading ? 'Loading…' : 'No quota changes recorded yet.'}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Tenant</th>
                <th>Changes</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((e) => (
                <tr key={e.id}>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                    {fmtDate(e.created_at)}
                  </td>
                  <td>
                    <strong>{e.tenant_name}</strong>
                    <div className="mono muted" style={{ fontSize: 11 }}>
                      {e.tenant_id}
                    </div>
                  </td>
                  <td className="mono">{fmtChanges(e.changes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card mt-16">
        <div className="card-title">
          API keys
          <span className="right muted" style={{ fontSize: 12 }}>
            {keys.length} total
          </span>
        </div>
        {keys.length === 0 ? (
          <div className="empty">{loading ? 'Loading…' : 'No keys issued yet.'}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Prefix</th>
                <th>Tenant</th>
                <th>IP whitelist</th>
                <th>Created</th>
                <th>Last used</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>{k.name}</td>
                  <td className="mono">{k.prefix}…</td>
                  <td className="mono">{k.tenant_id}</td>
                  <td className="muted">
                    {k.ip_whitelist.length ? k.ip_whitelist.join(', ') : 'any'}
                  </td>
                  <td className="muted">{fmtDate(k.created_at)}</td>
                  <td className="muted">{fmtDate(k.last_used_at)}</td>
                  <td>
                    <span className={`badge ${k.is_active ? 'ok' : 'err'}`}>
                      <span className="dot" />
                      {k.is_active ? 'active' : 'revoked'}
                    </span>
                  </td>
                  <td className="num">
                    {k.is_active && (
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => revoke(k.id)}
                        disabled={busy}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {editing && (
        <div className="dialog-backdrop" onClick={() => setEditing(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Quota — {editing.tenant_name}</h3>
            <p className="hint">
              Limits apply to new requests immediately. Caps are token totals
              per calendar day / month (UTC).
            </p>
            <div className="form-grid">
              <label className="field">
                <span>Requests per minute</span>
                <input
                  type="number"
                  min={1}
                  value={draft.rpm}
                  onChange={(e) => setDraft({ ...draft, rpm: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Tokens per minute</span>
                <input
                  type="number"
                  min={1}
                  value={draft.tpm}
                  onChange={(e) => setDraft({ ...draft, tpm: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Daily token cap</span>
                <input
                  type="number"
                  min={1}
                  value={draft.daily}
                  onChange={(e) => setDraft({ ...draft, daily: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Monthly token cap</span>
                <input
                  type="number"
                  min={1}
                  value={draft.monthly}
                  onChange={(e) => setDraft({ ...draft, monthly: e.target.value })}
                />
              </label>
            </div>
            <div className="row end">
              <button className="btn btn-ghost" onClick={() => setEditing(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={saveQuota} disabled={busy}>
                {busy ? <span className="spin" /> : 'Save quota'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
