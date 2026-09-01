import React, { useMemo, useState } from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'

type Candidate = {
  symbol: string
  timeframe: string
  direction: string
  entry_price: string | number
  stop_loss: string | number
  target: string | number
  risk_per_share: string | number
  reward: string | number
  risk_reward_ratio: string | number
  setup_name: string
}

type Evidence = {
  resistance: string | number
  breakout_candle_index: number
  breakout_candle_time: string
  retest_candle_index: number
  retest_candle_time: string
  confirmation_candle_index: number
  confirmation_candle_time: string
  atr_value: string | number
  volume_sma_value: string | number
  breakout_volume: number | null
  retest_low: string | number
  confirmation_volume: number | null
  decision: string
}

type StrategyResponse = {
  has_setup: boolean
  candidate: Candidate | null
  evidence: Evidence | null
  status: string
  reason?: string | null
}

function App() {
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('1d')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<StrategyResponse | null>(null)

  const baseUrl = useMemo(() => import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000', [])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!symbol.trim() || !timeframe.trim() || !start || !end) {
      setError('Please complete all fields before evaluating.')
      setResult(null)
      return
    }

    const startDate = new Date(start)
    const endDate = new Date(end)

    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      setError('Please enter valid date values.')
      setResult(null)
      return
    }

    if (startDate > endDate) {
      setError('Start date must be less than or equal to end date.')
      setResult(null)
      return
    }

    setLoading(true)
    setError('')

    try {
      const response = await fetch(`${baseUrl}/api/v1/strategy/evaluate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: symbol.trim(),
          timeframe,
          start: startDate.toISOString(),
          end: endDate.toISOString(),
        }),
      })

      if (!response.ok) {
        let detail = 'Request failed.'
        try {
          const payload = await response.json()
          detail = payload.detail ?? payload.message ?? detail
        } catch {
          detail = response.statusText || detail
        }
        throw new Error(detail)
      }

      const payload: StrategyResponse = await response.json()
      setResult(payload)
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Unexpected error.'
      setError(message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="panel">
        <header className="header-block">
          <p className="eyebrow">Strategy Evaluation</p>
          <h1>Swing Trading Assistant</h1>
        </header>

        <form className="strategy-form" onSubmit={handleSubmit}>
          <div className="field-group">
            <label htmlFor="symbol">Symbol</label>
            <input
              id="symbol"
              type="text"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="e.g. TST"
            />
          </div>

          <div className="field-row">
            <div className="field-group">
              <label htmlFor="timeframe">Timeframe</label>
              <select id="timeframe" value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
                <option value="1d">1d</option>
                <option value="4h">4h</option>
                <option value="1h">1h</option>
              </select>
            </div>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="start">Start date</label>
              <input id="start" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
            </div>

            <div className="field-group">
              <label htmlFor="end">End date</label>
              <input id="end" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
            </div>
          </div>

          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? 'Evaluating...' : 'Evaluate'}
          </button>
        </form>

        {error && <div className="status error">{error}</div>}

        {result && (
          <section className="result-card">
            <h2>Result</h2>
            <div className="result-grid">
              <div>
                <strong>Has setup:</strong> {String(result.has_setup)}
              </div>
              <div>
                <strong>Status:</strong> {result.status}
              </div>
              {result.reason ? (
                <div>
                  <strong>Reason:</strong> {result.reason}
                </div>
              ) : null}
            </div>

            {result.candidate && (
              <div className="section-box">
                <h3>Candidate</h3>
                <dl>
                  <div><dt>Symbol</dt><dd>{result.candidate.symbol}</dd></div>
                  <div><dt>Timeframe</dt><dd>{result.candidate.timeframe}</dd></div>
                  <div><dt>Direction</dt><dd>{result.candidate.direction}</dd></div>
                  <div><dt>Entry</dt><dd>{String(result.candidate.entry_price)}</dd></div>
                  <div><dt>Stop loss</dt><dd>{String(result.candidate.stop_loss)}</dd></div>
                  <div><dt>Target</dt><dd>{String(result.candidate.target)}</dd></div>
                  <div><dt>Risk per share</dt><dd>{String(result.candidate.risk_per_share)}</dd></div>
                  <div><dt>Reward</dt><dd>{String(result.candidate.reward)}</dd></div>
                  <div><dt>Risk/reward</dt><dd>{String(result.candidate.risk_reward_ratio)}</dd></div>
                  <div><dt>Setup</dt><dd>{result.candidate.setup_name}</dd></div>
                </dl>
              </div>
            )}

            {result.evidence && (
              <div className="section-box">
                <h3>Evidence</h3>
                <dl>
                  <div><dt>Resistance</dt><dd>{String(result.evidence.resistance)}</dd></div>
                  <div><dt>Breakout index</dt><dd>{String(result.evidence.breakout_candle_index)}</dd></div>
                  <div><dt>Breakout time</dt><dd>{result.evidence.breakout_candle_time}</dd></div>
                  <div><dt>Retest index</dt><dd>{String(result.evidence.retest_candle_index)}</dd></div>
                  <div><dt>Retest time</dt><dd>{result.evidence.retest_candle_time}</dd></div>
                  <div><dt>Confirmation index</dt><dd>{String(result.evidence.confirmation_candle_index)}</dd></div>
                  <div><dt>Confirmation time</dt><dd>{result.evidence.confirmation_candle_time}</dd></div>
                  <div><dt>ATR</dt><dd>{String(result.evidence.atr_value)}</dd></div>
                  <div><dt>Volume SMA</dt><dd>{String(result.evidence.volume_sma_value)}</dd></div>
                  <div><dt>Breakout volume</dt><dd>{String(result.evidence.breakout_volume)}</dd></div>
                  <div><dt>Retest low</dt><dd>{String(result.evidence.retest_low)}</dd></div>
                  <div><dt>Confirmation volume</dt><dd>{String(result.evidence.confirmation_volume)}</dd></div>
                  <div><dt>Decision</dt><dd>{result.evidence.decision}</dd></div>
                </dl>
              </div>
            )}
          </section>
        )}
      </section>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
