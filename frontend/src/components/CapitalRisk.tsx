import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'

type Props = {
  open: boolean
  onClose: () => void
  accountEquity: string
  riskPercent: string
  onEquityChange: (value: string) => void
  onRiskChange: (value: string) => void
  dataLive?: boolean
  lastCandleTime?: string | null
}

const EXAMPLE = {
  symbol: 'RELIANCE',
  entry: 2500,
  stop: 2450,
}

function formatInr(value: number): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatInrExact(value: number): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

export function CapitalRisk({
  open,
  onClose,
  accountEquity,
  riskPercent,
  onEquityChange,
  onRiskChange,
  dataLive,
  lastCandleTime,
}: Props) {
  const [draftEquity, setDraftEquity] = useState(accountEquity)
  const [draftRisk, setDraftRisk] = useState(riskPercent)
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (!open) return
    setDraftEquity(accountEquity)
    setDraftRisk(riskPercent)
    setSavedFlash(false)
  }, [open, accountEquity, riskPercent])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  const preview = useMemo(() => {
    const equity = Number(draftEquity)
    const riskPct = Number(draftRisk)
    const perShare = Math.abs(EXAMPLE.entry - EXAMPLE.stop)
    if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(riskPct) || riskPct <= 0 || perShare <= 0) {
      return null
    }
    const qty = Math.floor((equity * riskPct) / 100 / perShare)
    const atRisk = qty * perShare
    return { qty, atRisk }
  }, [draftEquity, draftRisk])

  function handleSave(event: FormEvent) {
    event.preventDefault()
    const equity = Number(draftEquity)
    const risk = Number(draftRisk)
    if (!Number.isFinite(equity) || equity < 0) return
    if (!Number.isFinite(risk) || risk <= 0 || risk > 100) return
    onEquityChange(String(equity))
    onRiskChange(String(risk))
    setSavedFlash(true)
    window.setTimeout(() => setSavedFlash(false), 1800)
  }

  if (!open) return null

  return createPortal(
    <div className="capital-risk-overlay" role="presentation">
      <div
        className="capital-risk-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="capital-risk-title"
      >
        <form className="capital-risk-card" onSubmit={handleSave}>
          <div className="capital-risk-modal-head">
            <h1 id="capital-risk-title">Your capital &amp; risk</h1>
            <button type="button" className="ghost-btn capital-risk-close" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>

          <label className="field capital-risk-field" htmlFor="capital-equity">
            <span>Account capital</span>
            <input
              id="capital-equity"
              type="number"
              min="0"
              step="1000"
              value={draftEquity}
              onChange={(e) => setDraftEquity(e.target.value)}
              autoFocus
            />
            <strong className="capital-risk-display">{formatInr(Number(draftEquity))}</strong>
          </label>

          <label className="field capital-risk-field" htmlFor="capital-risk">
            <span>Risk per trade</span>
            <div className="capital-risk-pct-row">
              <input
                id="capital-risk"
                type="number"
                min="0.1"
                max="100"
                step="0.1"
                value={draftRisk}
                onChange={(e) => setDraftRisk(e.target.value)}
              />
              <span className="capital-risk-pct-suffix">%</span>
            </div>
          </label>

          <div className="capital-risk-example" role="status">
            {preview ? (
              <>
                Example sizing: {EXAMPLE.symbol} entry {formatInrExact(EXAMPLE.entry)} stop{' '}
                {formatInrExact(EXAMPLE.stop)} → {preview.qty.toLocaleString('en-IN')} shares ·{' '}
                {formatInrExact(preview.atRisk)} at risk.
              </>
            ) : (
              <>Enter a valid capital and risk % to preview example sizing.</>
            )}
          </div>

          <div className="capital-risk-actions">
            <button type="submit" className="primary-button">
              Save
            </button>
            <p className="capital-risk-note">Engine owns Entry/SL — risk % only sizes qty.</p>
            {savedFlash ? <span className="capital-risk-saved">Saved to workspace</span> : null}
          </div>

          <footer className="home-hub-footer capital-risk-footer">
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
          </footer>
          <p className="capital-risk-disclaimer">
            Disclaimer: All trades involve risk. Past performance is not indicative of future results.
          </p>
        </form>
      </div>
    </div>,
    document.body,
  )
}
