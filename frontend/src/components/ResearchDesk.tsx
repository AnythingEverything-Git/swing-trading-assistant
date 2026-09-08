import { useState } from 'react'

type Props = {
  baseUrl: string
}

type Tab = 'overview' | 'technical' | 'fundamentals' | 'news' | 'fno' | 'similar'

export function ResearchDesk({ baseUrl }: Props) {
  const [symbol, setSymbol] = useState('RELIANCE')
  const [tab, setTab] = useState<Tab>('overview')
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [swingFit, setSwingFit] = useState<string | null>(null)
  const [orbNote, setOrbNote] = useState<string | null>(null)

  async function load(symOverride?: string) {
    const sym = (symOverride ?? symbol).trim().toUpperCase()
    if (!sym) return
    setSymbol(sym)
    setLoading(true)
    setError('')
    try {
      const [overviewRes, technicalRes, newsRes, fnoRes, similarRes] = await Promise.all([
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/overview`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/technical`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/news-events`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/fno`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/similar-setups`),
      ])
      const ov = overviewRes.ok ? await overviewRes.json() : null
      const tech = technicalRes.ok ? await technicalRes.json() : null
      const news = newsRes.ok ? await newsRes.json() : null
      const fno = fnoRes.ok ? await fnoRes.json() : null
      const similar = similarRes.ok ? await similarRes.json() : null
      setPayload({ overview: ov, technical: tech, news, fundamentals: ov, fno, similar, symbol: sym })
      setSwingFit(tech ? 'Technical snapshot loaded' : 'No technical data')
      setOrbNote('ORB eligibility: open Intraday morning board for live RVOL/OR rank')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Research failed')
    } finally {
      setLoading(false)
    }
  }

  function tabPayload() {
    if (!payload) return null
    if (tab === 'technical') return payload.technical
    if (tab === 'news') return payload.news
    if (tab === 'fundamentals') return payload.fundamentals || payload.overview
    if (tab === 'fno') return payload.fno
    if (tab === 'similar') return payload.similar
    return payload.overview
  }

  const overview = (payload?.overview || {}) as Record<string, unknown>

  return (
    <section className="panel research-desk wireframe-research">
      <header className="research-topbar">
        <div>
          <p className="eyebrow">TradePilot</p>
          <h1>Symbol Workspace</h1>
        </div>
        <label className="research-search">
          <span className="visually-hidden">Search symbol</span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void load()
            }}
            placeholder="Search symbol"
          />
          <button type="button" className="primary-button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Loading…' : 'Load'}
          </button>
        </label>
        <span className="research-mode-tag">FA and TA</span>
      </header>

      <div className="research-tabs" role="tablist">
        {(
          [
            ['overview', 'Overview'],
            ['technical', 'Technical'],
            ['fundamentals', 'Fundamentals'],
            ['news', 'News Events'],
            ['fno', 'F&O'],
            ['similar', 'Similar'],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? 'research-tab active' : 'research-tab'}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <div className="status error">{error}</div>}

      <div className="research-workspace">
        <div className="research-main">
          <div className="research-chart-placeholder">
            <p>Chart · {symbol || '—'}</p>
            <div className="research-level-lines">
              <span>Target</span>
              <span>Entry</span>
              <span>SL</span>
            </div>
            <pre className="research-json">
              {payload ? JSON.stringify(tabPayload(), null, 2) : 'Load a symbol to see FA/TA panels.'}
            </pre>
          </div>
          <div className="research-actions">
            <button type="button" className="primary-button" onClick={() => void load()} disabled={loading}>
              Evaluate
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setTab('technical')}
              disabled={!payload}
            >
              Backtest
            </button>
          </div>
        </div>

        <aside className="research-side">
          <div className="research-side-card">
            <h3>FA Snapshot</h3>
            <dl className="research-dl">
              <div>
                <dt>Market / sector</dt>
                <dd>{String(overview.sector || overview.industry || '—')}</dd>
              </div>
              <div>
                <dt>Last / change</dt>
                <dd>
                  {overview.current_price != null ? String(overview.current_price) : '—'}
                  {overview.change_pct != null ? ` (${String(overview.change_pct)}%)` : ''}
                </dd>
              </div>
              <div>
                <dt>Caution flags</dt>
                <dd>None flagged in workspace</dd>
              </div>
            </dl>
          </div>
          <div className="research-side-card">
            <h3>Technical setup fit</h3>
            <p className="research-fit-title">{swingFit || '—'}</p>
            <p className="field-hint">{orbNote}</p>
            <div className="research-fit-badges">
              <span className="intraday-reason armed">Swing: {swingFit || '—'}</span>
              <span className="intraday-reason muted">Intraday: open morning board</span>
            </div>
          </div>
        </aside>
      </div>
    </section>
  )
}
