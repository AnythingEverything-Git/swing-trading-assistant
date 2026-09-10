import { useEffect, useMemo, useState, type FormEvent } from 'react'

type Props = {
  accountEquity: string
  riskPercent: string
  onEquityChange: (value: string) => void
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
  accountEquity,
  riskPercent,
  onEquityChange,
  onRiskChange,
  embedded = false,
}: Props) {
  const [draftEquity, setDraftEquity] = useState(accountEquity)
  const [draftRisk, setDraftRisk] = useState(riskPercent)
  const [stopDistance, setStopDistance] = useState(String(EXAMPLE.entry - EXAMPLE.stop))
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    setDraftEquity(accountEquity)
    setDraftRisk(riskPercent)
  }, [accountEquity, riskPercent])

  const preview = useMemo(() => {
    const equity = Number(draftEquity)
    const riskPct = Number(draftRisk)
    const perShare = Math.abs(Number(stopDistance))
    if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(riskPct) || riskPct <= 0 || perShare <= 0) {
      return null
    }
    const qty = Math.floor((equity * riskPct) / 100 / perShare)
    const atRisk = qty * perShare
    return { qty, atRisk, perShare }
  }, [draftEquity, draftRisk, stopDistance])

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

  return (
    <form
      className={`risk-coach-panel${embedded ? ' is-embedded' : ''}`}
      onSubmit={handleSave}
      aria-label="Risk coach"
    >
      <header className="risk-coach-head">
        <h2>Risk coach</h2>
        <p className="risk-coach-rec">Recommended: Risk 0.5–1% of capital per trade</p>
      </header>

      <label className="field">
        <span>Account capital</span>
        <input
          type="number"
          min="0"
          step="1000"
          value={draftEquity}
          onChange={(e) => setDraftEquity(e.target.value)}
        />
        <strong className="risk-coach-display">{formatInr(Number(draftEquity) || 0)}</strong>
      </label>

      <label className="field">
        <span>Risk per trade</span>
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
        {preview ? (
          <p>
            Preview: {formatInr(Number(draftEquity) || 0)} × {draftRisk}% / {formatInr(preview.perShare, 2)} ={' '}
            <strong>{preview.qty} shares</strong> · at risk {formatInr(preview.atRisk, 2)}
          </p>
        ) : (
          <p>Enter a valid capital, risk %, and stop distance to preview sizing.</p>
        )}
      </div>

      <div className="risk-coach-actions">
        <button type="submit" className="primary-button">
          Save capital
        </button>
        <p className="field-hint">Note: Does not change strategy Entry/SL</p>
        {savedFlash ? <span className="risk-coach-saved">Saved to workspace</span> : null}
      </div>
    </form>
  )
}
