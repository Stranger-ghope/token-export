import { useRef, useState } from 'react'

interface Msg {
  role: 'user' | 'assistant'
  content: string
}

const MODELS = [
  'deepseek-chat',
  'qwen-plus',
  'gpt-4o',
  'gpt-4o-mini',
  'claude-3-5-sonnet-latest',
  'baichuan4',
]

const PROVIDERS = ['', 'deepseek', 'qwen', 'openai', 'anthropic', 'baichuan']

const KEY_STORAGE = 'tg_tenant_key'

export default function Playground() {
  const [apiKey, setApiKey] = useState(() => {
    try {
      return localStorage.getItem(KEY_STORAGE) || ''
    } catch {
      return ''
    }
  })
  const [model, setModel] = useState(MODELS[0])
  const [provider, setProvider] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [stream, setStream] = useState(true)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [meta, setMeta] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const saveKey = (v: string) => {
    setApiKey(v)
    try {
      if (v) localStorage.setItem(KEY_STORAGE, v)
      else localStorage.removeItem(KEY_STORAGE)
    } catch {
      /* ignore */
    }
  }

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    if (!apiKey.trim()) {
      setError('Enter a tenant API key in the panel first.')
      return
    }
    setError(null)
    setMeta(null)
    setReply('')
    setBusy(true)

    const history: Msg[] = [...messages, { role: 'user', content: text }]
    setMessages(history)
    setInput('')

    const body: Record<string, unknown> = {
      model,
      messages: history,
      temperature,
      stream,
    }
    if (provider) body.provider = provider

    const started = performance.now()
    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey.trim()}`,
        },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        let detail = res.statusText
        try {
          const j = await res.json()
          detail = j?.error?.message || j?.detail || JSON.stringify(j)
        } catch {
          /* keep statusText */
        }
        throw new Error(`${res.status} — ${detail}`)
      }

      let text_out = ''
      if (stream && res.body) {
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''
          for (const line of lines) {
            const t = line.trim()
            if (!t.startsWith('data:')) continue
            const payload = t.slice(5).trim()
            if (payload === '[DONE]') continue
            try {
              const j = JSON.parse(payload)
              const delta = j?.choices?.[0]?.delta?.content
              if (delta) {
                text_out += delta
                setReply(text_out)
                bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
              }
            } catch {
              /* ignore partial frame */
            }
          }
        }
      } else {
        const j = await res.json()
        text_out = j?.choices?.[0]?.message?.content ?? JSON.stringify(j, null, 2)
        setReply(text_out)
        const u = j?.usage
        if (u) {
          setMeta(
            `prompt ${u.prompt_tokens} · completion ${u.completion_tokens} · total ${u.total_tokens} tokens`
          )
        }
      }

      const ms = Math.round(performance.now() - started)
      setMeta((m) => `${m ? m + ' · ' : ''}${ms} ms · ${stream ? 'streamed' : 'json'}`)
      setMessages((prev) => [...prev, { role: 'assistant', content: text_out }])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <h2>Playground</h2>
        <p>Test the proxy end-to-end — routing, streaming, PII masking and limits.</p>
      </div>

      <div className="play-grid">
        <div className="card">
          <div className="card-title">Request settings</div>

          <label className="field">
            <span>Tenant API key</span>
            <input
              type="password"
              value={apiKey}
              placeholder="tg_..."
              onChange={(e) => saveKey(e.target.value)}
            />
          </label>

          <label className="field">
            <span>Model</span>
            <input
              type="text"
              list="model-list"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
            <datalist id="model-list">
              {MODELS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>

          <label className="field">
            <span>Provider override</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p === '' ? 'auto (by model name)' : p}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Temperature — {temperature.toFixed(2)}</span>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </label>

          <label className="row" style={{ marginBottom: 12, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={stream}
              onChange={(e) => setStream(e.target.checked)}
              style={{ width: 'auto' }}
            />
            Stream (SSE)
          </label>

          <div className="row">
            <button className="btn btn-ghost btn-sm" onClick={() => { setMessages([]); setReply(''); setMeta(null); setError(null) }}>
              Clear chat
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-title">
            Conversation
            <span className="right muted" style={{ fontSize: 12 }}>
              {model}
            </span>
          </div>

          {error && <div className="banner err">{error}</div>}

          <div className="chat-scroll">
            {messages.length === 0 && !reply && (
              <div className="empty">
                Send a message to test <code>/v1/chat/completions</code>.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="msg-role">{m.role}</div>
                <div className="msg-body">{m.content}</div>
              </div>
            ))}
            {busy && (reply || !error) && (
              <div className="msg assistant">
                <div className="msg-role">assistant</div>
                <div className="msg-body">
                  {reply || '…'}
                  {stream && <span className="cursor" />}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {meta && (
            <div className="muted mt-8" style={{ fontSize: 12 }}>
              {meta}
            </div>
          )}

          <div className="row mt-16" style={{ alignItems: 'flex-end' }}>
            <div style={{ flex: 1, minWidth: 240 }}>
              <textarea
                value={input}
                placeholder="Ask something…"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
              />
            </div>
            <button className="btn btn-primary" onClick={send} disabled={busy || !input.trim()}>
              {busy ? <span className="spin" /> : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
