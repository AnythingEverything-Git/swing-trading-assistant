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

type BacktestTrade = {
  entry_time: string
  entry_price: string | number
  exit_time: string
  exit_price: string | number
  quantity: number
  risk_amount: string | number
  pnl: string | number
  exit_reason: string
}

type BacktestResponse = {
  symbol: string
  timeframe: string
  completed_trades: number
  trades: BacktestTrade[]
  metrics: {
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: string | number
    total_pnl: string | number
    average_pnl: string | number
    total_r: string | number
    average_r: string | number
    maximum_drawdown: string | number
  }
}

function App() {
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('1d')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [accountEquity, setAccountEquity] = useState('10000')
  const [riskPercent, setRiskPercent] = useState('1')
  const [loading, setLoading] = useState(false)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [error, setError] = useState('')
  const [backtestError, setBacktestError] = useState('')
  const [result, setResult] = useState<StrategyResponse | null>(null)
  const [backtestResult, setBacktestResult] = useState<BacktestResponse | null>(null)

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

  const handleBacktest = async () => {
    if (!symbol.trim() || !timeframe.trim() || !start || !end || !accountEquity || !riskPercent) {
      setBacktestError('Please complete the backtest fields before running.')
      setBacktestResult(null)
      return
    }

    const startDate = new Date(start)
    const endDate = new Date(end)
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime()) || startDate > endDate) {
      setBacktestError('Please enter a valid date range for the backtest.')
      setBacktestResult(null)
      return
    }

    setBacktestLoading(true)
    setBacktestError('')
    try {
      const response = await fetch(`${baseUrl}/api/v1/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: symbol.trim(),
          timeframe,
          start: startDate.toISOString(),
          end: endDate.toISOString(),
          account_equity: accountEquity,
          risk_percent: riskPercent,
        }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail ?? 'Backtest request failed.')
      }

      setBacktestResult(await response.json() as BacktestResponse)
    } catch (caughtError) {
      setBacktestError(caughtError instanceof Error ? caughtError.message : 'Unexpected error.')
      setBacktestResult(null)
    } finally {
      setBacktestLoading(false)
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

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="account-equity">Account equity</label>
              <input id="account-equity" type="number" min="0" step="0.01" value={accountEquity} onChange={(event) => setAccountEquity(event.target.value)} />
            </div>
            <div className="field-group">
              <label htmlFor="risk-percent">Risk %</label>
              <input id="risk-percent" type="number" min="0" step="0.01" value={riskPercent} onChange={(event) => setRiskPercent(event.target.value)} />
            </div>
          </div>

          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? 'Evaluating...' : 'Evaluate'}
          </button>
          <button type="button" className="secondary-button" onClick={handleBacktest} disabled={backtestLoading}>
            {backtestLoading ? 'Running backtest...' : 'Run backtest'}
          </button>
        </form>

        {error && <div className="status error">{error}</div>}
        {backtestError && <div className="status error">{backtestError}</div>}

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

        {backtestResult && (
          <section className="result-card">
            <h2>Backtest results</h2>
            <div className="result-grid">
              <div><strong>Completed trades:</strong> {backtestResult.completed_trades}</div>
              <div><strong>Symbol:</strong> {backtestResult.symbol}</div>
              <div><strong>Timeframe:</strong> {backtestResult.timeframe}</div>
              <div><strong>Total trades:</strong> {backtestResult.metrics.total_trades}</div>
              <div><strong>Winning trades:</strong> {backtestResult.metrics.winning_trades}</div>
              <div><strong>Losing trades:</strong> {backtestResult.metrics.losing_trades}</div>
              <div><strong>Win rate:</strong> {String(backtestResult.metrics.win_rate)}%</div>
              <div><strong>Total P&amp;L:</strong> {String(backtestResult.metrics.total_pnl)}</div>
              <div><strong>Average P&amp;L:</strong> {String(backtestResult.metrics.average_pnl)}</div>
              <div><strong>Total R:</strong> {String(backtestResult.metrics.total_r)}</div>
              <div><strong>Average R:</strong> {String(backtestResult.metrics.average_r)}</div>
              <div><strong>Maximum drawdown:</strong> {String(backtestResult.metrics.maximum_drawdown)}</div>
            </div>
            {backtestResult.trades.length === 0 ? (
              <div className="empty-state">No trades were generated for this history and risk configuration.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Entry</th><th>Exit</th><th>Quantity</th><th>Risk</th><th>P&amp;L</th><th>Exit reason</th></tr>
                  </thead>
                  <tbody>
                    {backtestResult.trades.map((trade, index) => (
                      <tr key={`${trade.entry_time}-${index}`}>
                        <td>{String(trade.entry_price)}<small>{trade.entry_time}</small></td>
                        <td>{String(trade.exit_price)}<small>{trade.exit_time}</small></td>
                        <td>{trade.quantity}</td>
                        <td>{String(trade.risk_amount)}</td>
                        <td>{String(trade.pnl)}</td>
                        <td>{trade.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
