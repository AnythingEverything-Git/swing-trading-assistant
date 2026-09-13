import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { ORB_V1_RULES } from '../terminology'
import {
  applyTradepilotSplit,
  rebuildProfile,
  type RiskProfile,
} from '../riskProfile'

type Props = {
  profile: RiskProfile
  onProfileChange: (profile: RiskProfile) => void
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
export function RiskCoachPanel({ profile, onProfileChange, embedded = false }: Props) {
  const [draft, setDraft] = useState(profile)
  const [stopDistance, setStopDistance] = useState(String(EXAMPLE.entry - EXAMPLE.stop))
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    setDraft(profile)
  }, [profile])

  const live = useMemo(
    () =>
      rebuildProfile({
        allocationMode: draft.allocationMode,
        totalEquity: draft.totalEquity,
        swingPct: draft.swingPct,
        intradayPct: draft.intradayPct,
        reservePct: draft.reservePct,
        swingEquity: draft.swingEquity,
        intradayEquity: draft.intradayEquity,
        reserveEquity: draft.reserveEquity,
        swingRiskPerTradeInr: draft.swingRiskPerTradeInr,
        swingMaxOpenRiskInr: draft.swingMaxOpenRiskInr,
        intradayRiskPerTradeInr: draft.intradayRiskPerTradeInr,
        intradayMaxOpenRiskInr: draft.intradayMaxOpenRiskInr,
        intradayDailyLossInr: draft.intradayDailyLossInr,
      }),
    [draft],
  )

  const splitActive = live.allocationMode === 'tradepilot_split'

  const swingPreview = useMemo(() => {
    const riskBudget = Number(live.swingRiskPerTradeInr)
    const perShare = Math.abs(Number(stopDistance))
    const equity = Number(live.swingEquity)
    if (!Number.isFinite(riskBudget) || riskBudget <= 0 || perShare <= 0 || equity <= 0) return null
    const qty = Math.min(Math.floor(riskBudget / perShare), Math.floor(equity / EXAMPLE.entry))
    return { qty: Math.max(0, qty), atRisk: Math.max(0, qty) * perShare, perShare }
  }, [live.swingEquity, live.swingRiskPerTradeInr, stopDistance])

  const intraPreview = useMemo(() => {
    const equity = Number(live.intradayEquity)
    const pctBudget = (equity * ORB_V1_RULES.riskPerTradePct) / 100
    const abs = Number(live.intradayRiskPerTradeInr)
    const riskBudget = Math.min(pctBudget, Number.isFinite(abs) && abs > 0 ? abs : pctBudget)
    const perShare = Math.abs(Number(stopDistance))
    if (!Number.isFinite(equity) || equity <= 0 || perShare <= 0 || !Number.isFinite(riskBudget)) {
      return null
    }
    const qty = Math.min(Math.floor(riskBudget / perShare), Math.floor(equity / EXAMPLE.entry))
    return { qty: Math.max(0, qty), atRisk: Math.max(0, qty) * perShare, perShare, riskBudget }
  }, [live.intradayEquity, live.intradayRiskPerTradeInr, stopDistance])

  function patch(partial: Partial<RiskProfile>) {
    setDraft((prev) => ({ ...prev, ...partial }))
  }

  function handleSave(event: FormEvent) {
    event.preventDefault()
    const next = rebuildProfile({
      allocationMode: draft.allocationMode,
      totalEquity: draft.totalEquity,
      swingPct: draft.swingPct,
      intradayPct: draft.intradayPct,
      reservePct: draft.reservePct,
      swingEquity: draft.swingEquity,
      intradayEquity: draft.intradayEquity,
      reserveEquity: draft.reserveEquity,
      swingRiskPerTradeInr: draft.swingRiskPerTradeInr,
      swingMaxOpenRiskInr: draft.swingMaxOpenRiskInr,
      intradayRiskPerTradeInr: draft.intradayRiskPerTradeInr,
      intradayMaxOpenRiskInr: draft.intradayMaxOpenRiskInr,
      intradayDailyLossInr: draft.intradayDailyLossInr,
    })
    if (Number(next.totalEquity) < 0) return
    if (Number(next.swingRiskPerTradeInr) <= 0) return
    onProfileChange(next)
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
          Enter capital, then optionally apply TradePilot Split (70/20/10). Save to use desks for sizing and
          practice. Wallets update after every closed trade.
        </p>
      </header>

      <label className="field">
        <span>Total capital</span>
        <input
          type="number"
          min="0"
          step="1"
          value={draft.totalEquity}
          onChange={(e) => {
            const totalEquity = e.target.value
            if (draft.allocationMode === 'tradepilot_split') {
              setDraft(applyTradepilotSplit({ ...draft, totalEquity }))
            } else {
              patch({ totalEquity })
            }
          }}
        />
        <strong className="risk-coach-display">{formatInr(Number(live.totalEquity) || 0)}</strong>
      </label>

      <button
        type="button"
        className={`secondary-button${splitActive ? ' is-active-strategy' : ''}`}
        onClick={() => setDraft(applyTradepilotSplit(draft))}
      >
        TradePilot Split Strategy (70/20/10)
      </button>
      {splitActive ? (
        <button type="button" className="ghost-btn" onClick={() => patch({ allocationMode: 'manual' })}>
          Clear split · edit desks manually
        </button>
      ) : null}

      {splitActive ? (
        <div className="risk-coach-alloc-row">
          <div className="field">
            <span>Swing 70%</span>
            <strong className="risk-coach-display">{formatInr(Number(live.swingEquity) || 0)}</strong>
          </div>
          <div className="field">
            <span>Intraday 20%</span>
            <strong className="risk-coach-display">{formatInr(Number(live.intradayEquity) || 0)}</strong>
          </div>
          <div className="field">
            <span>Reserve 10%</span>
            <strong className="risk-coach-display">{formatInr(Number(live.reserveEquity) || 0)}</strong>
          </div>
        </div>
      ) : (
        <div className="risk-coach-alloc-row">
          <label className="field">
            <span>Swing ₹</span>
            <input
              type="number"
              min="0"
              step="1"
              value={draft.swingEquity}
              onChange={(e) => patch({ swingEquity: e.target.value, allocationMode: 'manual' })}
            />
          </label>
          <label className="field">
            <span>Intraday ₹</span>
            <input
              type="number"
              min="0"
              step="1"
              value={draft.intradayEquity}
              onChange={(e) => patch({ intradayEquity: e.target.value, allocationMode: 'manual' })}
            />
          </label>
          <label className="field">
            <span>Reserve ₹</span>
            <input
              type="number"
              min="0"
              step="1"
              value={draft.reserveEquity}
              onChange={(e) => patch({ reserveEquity: e.target.value, allocationMode: 'manual' })}
            />
          </label>
        </div>
      )}

      <label className="field">
        <span>Swing max risk / trade (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={draft.swingRiskPerTradeInr}
          onChange={(e) => patch({ swingRiskPerTradeInr: e.target.value })}
        />
        <span className="field-hint">≈ {live.riskPercent}% of swing bucket</span>
      </label>

      <label className="field">
        <span>Intraday max risk / trade (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={draft.intradayRiskPerTradeInr}
          onChange={(e) => patch({ intradayRiskPerTradeInr: e.target.value })}
        />
      </label>

      <label className="field">
        <span>Swing max open risk (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={draft.swingMaxOpenRiskInr}
          onChange={(e) => patch({ swingMaxOpenRiskInr: e.target.value })}
        />
      </label>

      <label className="field">
        <span>Intraday max open risk (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={draft.intradayMaxOpenRiskInr}
          onChange={(e) => patch({ intradayMaxOpenRiskInr: e.target.value })}
        />
      </label>

      <label className="field">
        <span>Intraday daily loss lock (₹)</span>
        <input
          type="number"
          min="1"
          step="1"
          value={draft.intradayDailyLossInr}
          onChange={(e) => patch({ intradayDailyLossInr: e.target.value })}
        />
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
          <strong>Math:</strong> min(bucket × %, ₹ cap) / stop distance = qty
        </p>
        {swingPreview ? (
          <p>
            Swing: budget {formatInr(Number(live.swingRiskPerTradeInr) || 0)} /{' '}
            {formatInr(swingPreview.perShare, 2)} = <strong>{swingPreview.qty} shares</strong> · at risk{' '}
            {formatInr(swingPreview.atRisk, 2)}
          </p>
        ) : (
          <p>Enter valid swing capital, risk ₹, and stop distance to preview.</p>
        )}
        {intraPreview ? (
          <p>
            Intraday: budget {formatInr(intraPreview.riskBudget, 2)} / {formatInr(intraPreview.perShare, 2)} ={' '}
            <strong>{intraPreview.qty} shares</strong> · at risk {formatInr(intraPreview.atRisk, 2)}
          </p>
        ) : (
          <p>Enter valid intraday capital and stop distance to preview ORB sizing.</p>
        )}
      </div>

      <div className="risk-coach-actions">
        <button type="submit" className="primary-button">
          Save allocation
        </button>
        <p className="field-hint">Note: Does not change strategy Entry/SL</p>
        {savedFlash ? <span className="risk-coach-saved">Saved to workspace</span> : null}
      </div>
    </form>
  )
}
