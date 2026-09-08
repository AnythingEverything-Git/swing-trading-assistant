import { useMemo, useState } from 'react'
import { createPortal } from 'react-dom'

export type DataReadinessStatus = {
  data_source: string
  live_ready: boolean
  claim: string
  last_candle_time: string | null
  symbols_with_candles: number
  symbols_with_1m?: number
  last_1m_candle_time?: string | null
  stale_risk?: string
  plug_and_play?: string
  environment?: string
}

type CoverageRow = {
  symbol: string
  has1d: boolean
  has1m: boolean
  status: 'OK' | 'Stale' | 'Gap'
}

type Props = {
  status: DataReadinessStatus | null
  formatDateTime: (value: string | null | undefined) => string
  onRefresh: () => Promise<void>
  coverageRows?: CoverageRow[]
}

function BarCell({ filled, dashed }: { filled: boolean; dashed?: boolean }) {
  return (
    <span
      className={`data-ready-bar ${filled ? 'filled' : ''} ${dashed && !filled ? 'dashed' : ''}`}
      aria-label={filled ? 'present' : 'missing'}
    />
  )
}

export function DataReadinessBanner({ status, formatDateTime, onRefresh, coverageRows }: Props) {
  const [refreshing, setRefreshing] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [coverageOpen, setCoverageOpen] = useState(false)

  const source = (status?.data_source ?? 'demo').toLowerCase()
  const sourceLabel = source === 'upstox' ? 'Live' : source === 'demo' ? 'Demo' : source
  const count1d = status?.symbols_with_candles ?? 0
  const count1m = status?.symbols_with_1m ?? 0
  const coverageLabel =
    count1d > 0 ? `${Math.min(count1m, count1d)}/${count1d} symbols` : '—/—'
  const staleRisk = status?.stale_risk ?? (status?.live_ready ? 'Low' : 'High')
  const warnScan = staleRisk === 'High' || !status?.live_ready || (count1d > 0 && count1m < count1d * 0.9)
  const isDemo = source === 'demo' || !status?.live_ready

  const rows = useMemo<CoverageRow[]>(() => {
    if (coverageRows && coverageRows.length > 0) return coverageRows
    if (!status || !warnScan) return []
    return [
      { symbol: 'RELIANCE', has1d: true, has1m: count1m > 0, status: count1m > 0 ? 'OK' : 'Gap' },
      { symbol: 'TCS', has1d: true, has1m: false, status: 'Stale' },
      { symbol: 'INFY', has1d: true, has1m: false, status: 'Stale' },
    ]
  }, [coverageRows, status, warnScan, count1m])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await onRefresh()
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <>
      <div
        className={`data-readiness-banner ${status?.live_ready ? 'live' : 'demo'} stale-${staleRisk.toLowerCase()}`}
        role="status"
      >
        <div className="data-readiness-facts">
          <span>
            Source <strong>{sourceLabel}</strong>
          </span>
          <span>
            Last 1d bar{' '}
            <strong>
              {status?.last_candle_time ? formatDateTime(status.last_candle_time) : '—:—'}
            </strong>
          </span>
          <span>
            1m coverage <strong>{coverageLabel}</strong>
          </span>
          <span>
            Stale risk <strong className={`stale-pill ${staleRisk.toLowerCase()}`}>{staleRisk}</strong>
          </span>
        </div>
        <div className="data-readiness-actions">
          <button type="button" className="secondary-button" onClick={() => void handleRefresh()} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh data'}
          </button>
          <button type="button" className="secondary-button" onClick={() => setHelpOpen(true)}>
            What does this mean?
          </button>
          {rows.length > 0 && (
            <button type="button" className="link-button" onClick={() => setCoverageOpen((v) => !v)}>
              {coverageOpen ? 'Hide coverage' : 'Coverage gaps'}
            </button>
          )}
        </div>
      </div>

      {coverageOpen && rows.length > 0 && (
        <div className="data-coverage-panel">
          <div className="data-coverage-warn">
            <strong>Do not scan until coverage improves.</strong>
            <span>
              {isDemo
                ? 'You are on demo candles — fine for learning, not for live market decisions.'
                : status?.claim ?? 'Some symbols are missing fresh bars.'}
            </span>
          </div>
          <div className="table-wrap data-coverage-table-wrap">
            <table className="data-coverage-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>1d</th>
                  <th>1m</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.symbol}>
                    <td>{row.symbol}</td>
                    <td>
                      <BarCell filled={row.has1d} />
                    </td>
                    <td>
                      <BarCell filled={row.has1m} dashed />
                    </td>
                    <td>
                      <span className={`coverage-status ${row.status.toLowerCase()}`}>{row.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {helpOpen
        ? createPortal(
            <div className="capital-risk-overlay" role="presentation">
              <div
                className="capital-risk-modal data-runbook-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="data-help-title"
              >
                <div className="capital-risk-card">
                  <div className="capital-risk-modal-head">
                    <h1 id="data-help-title">What this data status means</h1>
                    <button
                      type="button"
                      className="ghost-btn capital-risk-close"
                      onClick={() => setHelpOpen(false)}
                      aria-label="Close"
                    >
                      ×
                    </button>
                  </div>

                  <div className="data-help-summary">
                    <p>
                      TradePilot never pretends candles are live when they are not. This strip tells you whether
                      setups can be trusted right now.
                    </p>
                  </div>

                  <dl className="data-help-defs">
                    <div>
                      <dt>Source</dt>
                      <dd>
                        {isDemo
                          ? 'Demo sample candles for learning and UI testing — not the live NSE feed.'
                          : 'Live market data feed is connected.'}
                      </dd>
                    </div>
                    <div>
                      <dt>Last 1d bar</dt>
                      <dd>
                        Newest daily candle we have
                        {status?.last_candle_time
                          ? ` (${formatDateTime(status.last_candle_time)})`
                          : ' (none loaded yet)'}
                        . Used for swing scans.
                      </dd>
                    </div>
                    <div>
                      <dt>1m coverage</dt>
                      <dd>
                        How many symbols have intraday minute bars ({coverageLabel}). Morning board and OR charts
                        need this.
                      </dd>
                    </div>
                    <div>
                      <dt>Stale risk</dt>
                      <dd>
                        {staleRisk === 'High'
                          ? 'High — wait or refresh before treating ideas as live.'
                          : staleRisk === 'Medium'
                            ? 'Medium — data may lag; double-check last bar time.'
                            : 'Low — freshness looks healthy for trading decisions.'}
                      </dd>
                    </div>
                  </dl>

                  <div className="data-help-next">
                    <strong>What you can do now</strong>
                    <ol>
                      <li>
                        {isDemo
                          ? 'Keep using Demo to learn Swing / Intraday / Research safely.'
                          : 'If coverage looks thin, refresh status and avoid scanning until 1m catches up.'}
                      </li>
                      <li>Tap Refresh data to re-check Source, last bar, and coverage.</li>
                      <li>Open Coverage gaps to see example symbols that are OK vs missing bars.</li>
                    </ol>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={refreshing}
                      onClick={() => void handleRefresh()}
                    >
                      {refreshing ? 'Refreshing…' : 'Refresh data status'}
                    </button>
                  </div>

                  <details className="data-help-advanced">
                    <summary>Admin: how live candles get loaded</summary>
                    <p>
                      Connecting live Upstox data is an ops setup step (token + refresh jobs), not something this
                      button can invent. After live data is configured, use Refresh data to verify the banner.
                    </p>
                    <ul>
                      <li>Daily candles: market-data refresh job / script after market close</li>
                      <li>Intraday 1m: intraday watermark refresh or ensure-1m after Morning board</li>
                      <li>NSE master list: weekly universe rebuild from Upstox</li>
                    </ul>
                  </details>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  )
}
