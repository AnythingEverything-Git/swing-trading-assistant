import { createPortal } from 'react-dom'
import { useEffect } from 'react'

type Props = {
  open: boolean
  onClose: () => void
  guidedMode: boolean
  onSelectGuided: () => void
  onSelectPro: () => void
  onFindSetups: () => void
  onShowHowItWorks: () => void
  dataLive?: boolean
  lastCandleTime?: string | null
}

const DEMO_ROWS = [
  { reason: 'RANKED_ARMED', score: '₹18,000', symbol: 'RELIANCE' },
  { reason: 'BREAKOUT_NOT_TRIGGERED', score: '₹7,500', symbol: 'INFY' },
  { reason: 'TRADED', score: '₹12,200', symbol: 'HDFCBANK' },
]

function downloadDemoCsv() {
  const lines = ['reason,score,symbol', ...DEMO_ROWS.map((r) => `${r.reason},${r.score},${r.symbol}`)]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'tradepilot-pro-density-sample.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export function GuidedProMode({
  open,
  onClose,
  guidedMode,
  onSelectGuided,
  onSelectPro,
  onFindSetups,
  onShowHowItWorks,
  dataLive,
  lastCandleTime,
}: Props) {
  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [open])

  if (!open) return null

  return createPortal(
    <div className="guided-pro-overlay" role="presentation">
      <div
        className="guided-pro-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guided-pro-title"
      >
        <div className="guided-pro-modal-head">
          <h1 id="guided-pro-title">Guided vs Pro — same data, two densities</h1>
          <button type="button" className="ghost-btn capital-risk-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="guided-pro-split">
          <section className={`guided-pro-pane ${guidedMode ? 'is-active' : ''}`}>
            <h2>Guided mode</h2>
            <div className="guided-pro-actions-stack">
              <button type="button" className="primary-button guided-pro-big" onClick={onSelectGuided}>
                Buy
              </button>
              <button type="button" className="primary-button guided-pro-big short" onClick={onSelectGuided}>
                Sell short
              </button>
            </div>
            <div className="guided-pro-utility">
              <button type="button" className="secondary-button" onClick={onShowHowItWorks}>
                How this works tip
              </button>
              <button type="button" className="secondary-button" onClick={onFindSetups}>
                Find setups
              </button>
            </div>
            <p className="guided-pro-copy">
              Plain labels, one primary path, Top ideas first.
              <br />
              Active: <strong>{guidedMode ? 'Guided' : 'Pro'}</strong>
            </p>
            <button type="button" className="primary-button guided-pro-cta" onClick={onSelectGuided}>
              Use Guided
            </button>
          </section>

          <section className={`guided-pro-pane ${!guidedMode ? 'is-active' : ''}`}>
            <div className="guided-pro-pane-head">
              <h2>Pro mode</h2>
              <button type="button" className="secondary-button" onClick={downloadDemoCsv}>
                CSV export
              </button>
            </div>
            <table className="guided-pro-table">
              <thead>
                <tr>
                  <th>Reason</th>
                  <th>Score</th>
                  <th>Symbol</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_ROWS.map((row) => (
                  <tr key={`${row.symbol}-${row.reason}`}>
                    <td>
                      <code className="reason-code">{row.reason}</code>
                    </td>
                    <td className="num-cell">{row.score}</td>
                    <td>{row.symbol}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="guided-pro-keys">Keyboard hints: ↑↓ navigate, Enter select</p>
            <button type="button" className="primary-button guided-pro-cta" onClick={onSelectPro}>
              Use Pro
            </button>
          </section>
        </div>

        <div className="guided-pro-status">
          <div className="home-hub-data">
            <span className="home-hub-footer-icon home-hub-footer-icon-data" aria-hidden="true" />
            <span className="home-hub-footer-label">Data</span>
            <span className={`data-pill ${dataLive ? 'live' : 'demo'}`}>
              <span className="data-pill-dot" aria-hidden="true" />
              {dataLive ? 'live' : 'demo'}
            </span>
          </div>
          <div className="home-hub-candle">
            <span className="home-hub-footer-icon home-hub-footer-icon-clock" aria-hidden="true" />
            <span className="home-hub-footer-label">Last candle time:</span>
            <span className="home-hub-candle-box">{lastCandleTime || '—:—'}</span>
          </div>
        </div>
        <p className="guided-pro-disclaimer">Data is for educational purposes only.</p>
      </div>
    </div>,
    document.body,
  )
}
