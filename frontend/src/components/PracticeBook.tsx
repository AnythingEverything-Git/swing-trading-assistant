import { useEffect, useMemo, useState } from 'react'
import { listIntradayPractice, listIntradaySessions, type IntradayPracticeTrade } from '../intraday/api'

type SwingPaperRow = {
  id: number
  symbol: string
  status: string
  direction?: string
  entry_price?: string | number
  stop_loss?: string | number
  realized_pnl?: string | number | null
  opened_at?: string | null
  created_at?: string | null
}

type Props = {
  baseUrl: string
}

function formatPrice(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(n)
}

export function PracticeBook({ baseUrl }: Props) {
  const [tab, setTab] = useState<'swing' | 'intraday'>('swing')
  const [swing, setSwing] = useState<SwingPaperRow[]>([])
  const [intraday, setIntraday] = useState<IntradayPracticeTrade[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | string | null>(null)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const paperRes = await fetch(`${baseUrl}/api/v1/paper/trades?status=ALL`)
      if (paperRes.ok) {
        const body = (await paperRes.json()) as { trades?: SwingPaperRow[] }
        setSwing(body.trades || [])
      } else {
        setError(`Swing practice load failed (${paperRes.status})`)
      }
      const { sessions } = await listIntradaySessions(baseUrl, 5)
      const all: IntradayPracticeTrade[] = []
      for (const s of sessions.slice(0, 3)) {
        try {
          const listed = await listIntradayPractice(baseUrl, s.id)
          all.push(...listed.trades)
        } catch {
          /* skip */
        }
      }
      setIntraday(all)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load practice book')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [baseUrl])

  const openCount = useMemo(() => {
    if (tab === 'swing') return swing.filter((t) => t.status === 'OPEN' || t.status === 'PENDING').length
    return intraday.filter((t) => t.status === 'OPEN' || t.status === 'PENDING').length
  }, [tab, swing, intraday])

  const realized = useMemo(() => {
    if (tab === 'swing') {
      return swing.reduce((sum, t) => sum + (Number(t.realized_pnl) || 0), 0)
    }
    return intraday.reduce((sum, t) => sum + (Number((t as { realized_pnl?: number }).realized_pnl) || 0), 0)
  }, [tab, swing, intraday])

  const selectedSwing = swing.find((t) => t.id === selectedId)
  const selectedIntra = intraday.find((t) => t.id === selectedId)

  return (
    <section className="panel practice-book wireframe-practice">
      <header className="header-block practice-book-head">
        <div>
          <p className="eyebrow">TradePilot</p>
          <h1>Unified Practice Book</h1>
        </div>
        <button type="button" className="secondary-button" onClick={() => void load()} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <div className="practice-tabs" role="tablist">
        <button
          type="button"
          className={tab === 'swing' ? 'practice-tab active' : 'practice-tab'}
          onClick={() => setTab('swing')}
        >
          Swing practice
        </button>
        <button
          type="button"
          className={tab === 'intraday' ? 'practice-tab active' : 'practice-tab'}
          onClick={() => setTab('intraday')}
        >
          Intraday practice
        </button>
      </div>

      <div className="practice-stats">
        <div className="practice-stat-card">
          <span>Open count</span>
          <strong>{openCount}</strong>
        </div>
        <div className="practice-stat-card">
          <span>Realized PnL</span>
          <strong className={realized >= 0 ? 'pnl-pos' : 'pnl-neg'}>
            {realized >= 0 ? '+' : ''}
            {formatPrice(realized)}
          </strong>
        </div>
        <div className="practice-stat-card">
          <span>Claim</span>
          <p className="field-hint">Fake money only</p>
          <button type="button" className="secondary-button" disabled>
            Practice only
          </button>
        </div>
      </div>

      {error && <div className="status error">{error}</div>}

      <h3 className="practice-table-title">Table of trades</h3>
      <div className="table-wrap">
        {tab === 'swing' ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Desk</th>
                <th>Direction</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {swing.length === 0 && (
                <tr>
                  <td colSpan={7}>No swing practice trades yet.</td>
                </tr>
              )}
              {swing.map((t) => (
                <tr key={t.id} className={selectedId === t.id ? 'row-selected' : undefined}>
                  <td>{t.symbol}</td>
                  <td>Swing</td>
                  <td>{t.direction || '—'}</td>
                  <td className="num-cell">{formatPrice(t.entry_price)}</td>
                  <td className="num-cell">{formatPrice(t.stop_loss)}</td>
                  <td>
                    <span className={`status-pill ${String(t.status).toLowerCase()}`}>{t.status}</span>
                  </td>
                  <td>
                    <button type="button" className="link-button" onClick={() => setSelectedId(t.id)}>
                      →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Desk</th>
                <th>Direction</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {intraday.length === 0 && (
                <tr>
                  <td colSpan={7}>No intraday practice trades yet.</td>
                </tr>
              )}
              {intraday.map((t) => (
                <tr key={t.id} className={selectedId === t.id ? 'row-selected' : undefined}>
                  <td>{t.symbol}</td>
                  <td>Intraday</td>
                  <td>{t.direction || '—'}</td>
                  <td className="num-cell">{formatPrice(t.entry_price)}</td>
                  <td className="num-cell">{formatPrice(t.stop_loss)}</td>
                  <td>
                    <span className={`status-pill ${String(t.status).toLowerCase()}`}>{t.status}</span>
                  </td>
                  <td>
                    <button type="button" className="link-button" onClick={() => setSelectedId(t.id)}>
                      →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="practice-detail">
        <div className="practice-detail-head">
          <h3>Trade detail</h3>
        </div>
        {selectedSwing || selectedIntra ? (
          <pre className="research-json">{JSON.stringify(selectedSwing || selectedIntra, null, 2)}</pre>
        ) : (
          <p className="field-hint">Select a row to inspect plan levels and status.</p>
        )}
      </div>

      <footer className="practice-footer-claim">
        Practice is not a brokerage order. This is a simulated learning environment.
      </footer>
    </section>
  )
}
