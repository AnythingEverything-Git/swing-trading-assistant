import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { ORB_V1_RULES } from '../terminology'

type Props = {
  swingEquity: string
  intradayEquity: string
  riskPercent: string
  onSwingEquityChange: (value: string) => void
  onIntradayEquityChange: (value: string) => void
  onRiskChange: (value: string) => void
  embedded?: boolean
}

const EXAMPLE = { entry: 2500, stop: 2250 }

function formatInr(value: number, digits = 0): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: digits,
  }).format(value)
}

/** UC-F9 — sizing math only; never changes Entry/SL. */
export function RiskCoachPanel({
  swingEquity,
  intradayEquity,
  riskPercent,
  onSwingEquityChange,
  onIntradayEquityChange,
  onRiskChange,
  embedded = false,
}: Props) {
  const [draftSwing, setDraftSwing] = useState(swingEquity)
  const [draftIntra, setDraftIntra] = useState(intradayEquity)
  const [draftRisk, setDraftRisk] = useState(riskPercent)
  const [stopDistance, setStopDistance] = useState(String(EXAMPLE.entry - EXAMPLE.stop))
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    setDraftSwing(swingEquity)
    setDraftIntra(intradayEquity)
    setDraftRisk(riskPercent)
  }, [swingEquity, intradayEquity, riskPercent])

  const swingPreview = useMemo(() => {
    const equity = Number(draftSwing)
    const riskPct = Number(draftRisk)
    const perShare = Math.abs(Number(stopDistance))
    if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(riskPct) || riskPct <= 0 || perShare <= 0) {
      return null
    }
    const qty = Math.floor((equity * riskPct) / 100 / perShare)
    const atRisk = qty * perShare
    return { qty, atRisk, perShare }
  }, [draftSwing, draftRisk, stopDistance])

  const intraPreview = useMemo(() => {
    const equity = Number(draftIntra)
    const riskPct = ORB_V1_RULES.riskPerTradePct
    const perShare = Math.abs(Number(stopDistance))
    if (!Number.isFinite(equity) || equity <= 0 || perShare <= 0) return null
    const qty = Math.floor((equity * riskPct) / 100 / perShare)
    const atRisk = qty * perShare
    return { qty, atRisk, perShare }
  }, [draftIntra, stopDistance])

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

  return (
    <form
      className={`risk-coach-panel${embedded ? ' is-embedded' : ''}`}
      onSubmit={handleSave}
      aria-label="Risk coach"
    >
      <header className="risk-coach-head">
        <h2>Risk coach</h2>
        <p className="risk-coach-rec">
          Separate Swing and Intraday capital. Swing risk is editable; Intraday ORB V1 locks risk at{' '}
          {ORB_V1_RULES.riskPerTradePct}%.
        </p>
      </header>

      <label className="field">
        <span>Swing capital</span>
        <input
          type="number"
          min="0"
          step="1000"
          value={draftSwing}
          onChange={(e) => setDraftSwing(e.target.value)}
        />
        <strong className="risk-coach-display">{formatInr(Number(draftSwing) || 0)}</strong>
      </label>

      <label className="field">
        <span>Intraday capital</span>
        <input
          type="number"
          min="0"
          step="1000"
          value={draftIntra}
          onChange={(e) => setDraftIntra(e.target.value)}
        />
        <strong className="risk-coach-display">{formatInr(Number(draftIntra) || 0)}</strong>
      </label>

      <label className="field">
        <span>Swing risk per trade</span>
        <div className="risk-coach-pct-row">
          <input
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            value={draftRisk}
            onChange={(e) => setDraftRisk(e.target.value)}
          />
          <span>%</span>
        </div>
      </label>

      <label className="field">
        <span>Example stop distance (₹)</span>
        <input
          type="number"
          min="0.01"
          step="1"
          value={stopDistance}
          onChange={(e) => setStopDistance(e.target.value)}
        />
      </label>

      <div className="risk-coach-math" role="status">
        <p>
          <strong>Math:</strong> Capital × risk% / stop distance = qty
        </p>
        {swingPreview ? (
          <p>
            Swing: {formatInr(Number(draftSwing) || 0)} × {draftRisk}% / {formatInr(swingPreview.perShare, 2)} ={' '}
            <strong>{swingPreview.qty} shares</strong> · at risk {formatInr(swingPreview.atRisk, 2)}
          </p>
        ) : (
          <p>Enter valid swing capital, risk %, and stop distance to preview.</p>
        )}
        {intraPreview ? (
          <p>
            Intraday: {formatInr(Number(draftIntra) || 0)} × {ORB_V1_RULES.riskPerTradePct}% /{' '}
            {formatInr(intraPreview.perShare, 2)} = <strong>{intraPreview.qty} shares</strong> · at risk{' '}
            {formatInr(intraPreview.atRisk, 2)}
          </p>
        ) : (
          <p>Enter valid intraday capital and stop distance to preview ORB sizing.</p>
        )}
      </div>

      <div className="risk-coach-actions">
        <button type="submit" className="primary-button">
          Save capitals
        </button>
        <p className="field-hint">Note: Does not change strategy Entry/SL</p>
        {savedFlash ? <span className="risk-coach-saved">Saved to workspace</span> : null}
      </div>
    </form>
  )
}
