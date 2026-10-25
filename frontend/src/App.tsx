import { useCallback, useEffect, useState } from 'react'
import Overview from './pages/Overview'
import Tenants from './pages/Tenants'
import Usage from './pages/Usage'
import Playground from './pages/Playground'
import { api, getAdminKey, setAdminKey, type Health } from './api'

type Page = 'overview' | 'tenants' | 'usage' | 'playground'

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: 'overview', label: 'Overview', icon: '◈' },
  { id: 'tenants', label: 'Tenants & Keys', icon: '⚿' },
  { id: 'usage', label: 'Usage', icon: '▤' },
  { id: 'playground', label: 'Playground', icon: '▶' },
]

const TITLES: Record<Page, string> = {
  overview: 'Overview',
  tenants: 'Tenants & API Keys',
  usage: 'Usage',
  playground: 'Playground',
}

function loadTheme(): 'light' | 'dark' {
  try {
    const saved = localStorage.getItem('tg_theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* ignore */
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  const [theme, setTheme] = useState<'light' | 'dark'>(loadTheme)
  const [health, setHealth] = useState<Health | null>(null)
  const [showKeyDialog, setShowKeyDialog] = useState(false)
  const [keyDraft, setKeyDraft] = useState('')
  const [keySaved, setKeySaved] = useState(!!getAdminKey())

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('tg_theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.get<Health>('/health', {}, false))
    } catch {
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    refreshHealth()
    const t = setInterval(refreshHealth, 15000)
    return () => clearInterval(t)
  }, [refreshHealth])

  const saveKey = () => {
    setAdminKey(keyDraft.trim())
    setKeySaved(!!keyDraft.trim())
    setShowKeyDialog(false)
    setKeyDraft('')
  }

  const up = health?.status === 'ok'

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">T</div>
          <div>
            Token Gateway
            <span className="brand-sub">AI routing console</span>
          </div>
        </div>
        <div className="nav-label">Console</div>
        {NAV.map((n) => (
          <button
            key={n.id}
            className={`nav-item ${page === n.id ? 'active' : ''}`}
            onClick={() => setPage(n.id)}
          >
            <span className="icon">{n.icon}</span>
            {n.label}
          </button>
        ))}
        <div className="sidebar-foot">
          {health ? (
            <>
              env <strong>{health.env}</strong> · db{' '}
              <strong>{health.db ? 'ok' : 'down'}</strong>
            </>
          ) : (
            'gateway unreachable'
          )}
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>{TITLES[page]}</h1>
          <span className={`badge ${up ? 'ok' : 'err'}`}>
            <span className="dot" />
            {up ? 'Healthy' : health ? health.status : 'Offline'}
          </span>
          <span className="spacer" />
          <a className="btn btn-ghost btn-sm" href="/docs" target="_blank" rel="noreferrer">
            API docs
          </a>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setKeyDraft(getAdminKey())
              setShowKeyDialog(true)
            }}
          >
            {keySaved ? '✓ Admin key' : 'Set admin key'}
          </button>
          <button
            className="btn-icon theme-toggle"
            title="Toggle light / dark"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </header>

        <main className="content">
          {page === 'overview' && (
            <Overview health={health} onRefresh={refreshHealth} onGo={setPage} />
          )}
          {page === 'tenants' && <Tenants />}
          {page === 'usage' && <Usage />}
          {page === 'playground' && <Playground />}
        </main>
      </div>

      {showKeyDialog && (
        <div className="dialog-backdrop" onClick={() => setShowKeyDialog(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Admin API key</h3>
            <p className="hint">
              Required for tenant, key and usage endpoints. Sent as{' '}
              <code>X-Admin-Key</code> and stored only in this browser.
            </p>
            <label className="field">
              <span>Key value</span>
              <input
                type="password"
                value={keyDraft}
                placeholder="ADMIN_API_KEY"
                onChange={(e) => setKeyDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && saveKey()}
                autoFocus
              />
            </label>
            <div className="row end">
              {keySaved && (
                <button
                  className="btn btn-danger"
                  onClick={() => {
                    setAdminKey('')
                    setKeySaved(false)
                    setShowKeyDialog(false)
                  }}
                >
                  Clear
                </button>
              )}
              <button className="btn btn-ghost" onClick={() => setShowKeyDialog(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={saveKey}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
