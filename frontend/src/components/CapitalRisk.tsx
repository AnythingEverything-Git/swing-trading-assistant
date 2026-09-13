import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { ORB_V1_RULES } from '../terminology'

type Props = {
  open: boolean
  onClose: () => void
  swingEquity: string
  intradayEquity: string
  riskPercent: string
  onSwingEquityChange: (value: string) => void
  onIntradayEquityChange: (value: string) => void
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

function sizePreview(equityRaw: string, riskPctRaw: string) {
  const equity = Number(equityRaw)
  const riskPct = Number(riskPctRaw)
  const perShare = Math.abs(EXAMPLE.entry - EXAMPLE.stop)
  if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(riskPct) || riskPct <= 0 || perShare <= 0) {
    return null
  }
  const qty = Math.floor((equity * riskPct) / 100 / perShare)
  const atRisk = qty * perShare
  return { qty, atRisk }
}

export function CapitalRisk({
  open,
  onClose,
  swingEquity,
  intradayEquity,
  riskPercent,
  onSwingEquityChange,
  onIntradayEquityChange,
  onRiskChange,
  dataLive,
  lastCandleTime,
}: Props) {
  const [draftSwing, setDraftSwing] = useState(swingEquity)
  const [draftIntra, setDraftIntra] = useState(intradayEquity)
  const [draftRisk, setDraftRisk] = useState(riskPercent)
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (!open) return
    setDraftSwing(swingEquity)
    setDraftIntra(intradayEquity)
    setDraftRisk(riskPercent)
    setSavedFlash(false)
  }, [open, swingEquity, intradayEquity, riskPercent])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  const swingPreview = useMemo(() => sizePreview(draftSwing, draftRisk), [draftSwing, draftRisk])
  const intraPreview = useMemo(
    () => sizePreview(draftIntra, String(ORB_V1_RULES.riskPerTradePct)),
    [draftIntra],
  )

  function handleSave(event: FormEvent) {
    event.preventDefault()
    const swing = Number(draftSwing)
    const intra = Number(draftIntra)
    const risk = Number(draftRisk)
    if (!Number.isFinite(swing) || swing < 0) return
    if (!Number.isFinite(intra) || intra < 0) return
    if (!Number.isFinite(risk) || risk <= 0 || risk > 100) return
    onSwingEquityChange(String(swing))
    onIntradayEquityChange(String(intra))
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
            <h1 id="capital-risk-title">Risk coach</h1>
            <button type="button" className="ghost-btn capital-risk-close" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
          <p className="field-hint capital-risk-rec">
            Swing and Intraday keep separate practice capital. Recommended swing risk: 0.5–1% per trade.
            Intraday ORB V1 uses a fixed {ORB_V1_RULES.riskPerTradePct}% risk.
          </p>

          <div className="capital-risk-fields capital-risk-fields-dual">
            <label className="field capital-risk-field" htmlFor="capital-swing-equity">
              <span>Swing capital</span>
              <input
                id="capital-swing-equity"
                type="number"
                min="0"
                step="1000"
                value={draftSwing}
                onChange={(e) => setDraftSwing(e.target.value)}
                autoFocus
              />
              <strong className="capital-risk-display">{formatInr(Number(draftSwing))}</strong>
            </label>

            <label className="field capital-risk-field" htmlFor="capital-intra-equity">
              <span>Intraday capital</span>
              <input
                id="capital-intra-equity"
                type="number"
                min="0"
                step="1000"
                value={draftIntra}
                onChange={(e) => setDraftIntra(e.target.value)}
              />
              <strong className="capital-risk-display">{formatInr(Number(draftIntra))}</strong>
            </label>

            <label className="field capital-risk-field" htmlFor="capital-risk">
              <span>Swing risk per trade</span>
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
          </div>

          <div className="capital-risk-example" role="status">
            <p>
              Swing example: {EXAMPLE.symbol} entry {formatInrExact(EXAMPLE.entry)} stop{' '}
              {formatInrExact(EXAMPLE.stop)}
              {swingPreview
                ? ` → ${swingPreview.qty.toLocaleString('en-IN')} shares · ${formatInrExact(swingPreview.atRisk)} at risk.`
                : ' — enter valid swing capital & risk %.'}
            </p>
            <p>
              Intraday example (ORB {ORB_V1_RULES.riskPerTradePct}% risk): same levels
              {intraPreview
                ? ` → ${intraPreview.qty.toLocaleString('en-IN')} shares · ${formatInrExact(intraPreview.atRisk)} at risk.`
                : ' — enter valid intraday capital.'}
            </p>
          </div>

          <div className="capital-risk-actions">
            <button type="submit" className="primary-button">
              Save capitals
            </button>
            <p className="capital-risk-note">Engine owns Entry/SL — capital only sizes qty per desk.</p>
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
