import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { ORB_V1_RULES } from '../terminology'
import {
  applyTradepilotSplit,
  rebuildProfile,
  type RiskProfile,
} from '../riskProfile'

type Props = {
  open: boolean
  onClose: () => void
  profile: RiskProfile
  onProfileChange: (profile: RiskProfile) => void
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

function sizePreview(equityRaw: string, riskBudgetInr: string) {
  const equity = Number(equityRaw)
  const riskBudget = Number(riskBudgetInr)
  const perShare = Math.abs(EXAMPLE.entry - EXAMPLE.stop)
  if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(riskBudget) || riskBudget <= 0 || perShare <= 0) {
    return null
  }
  const qty = Math.floor(riskBudget / perShare)
  const maxByCapital = Math.floor(equity / EXAMPLE.entry)
  const capped = Math.min(qty, Math.max(0, maxByCapital))
  return { qty: capped, atRisk: capped * perShare }
}

export function CapitalRisk({
  open,
  onClose,
  profile,
  onProfileChange,
  dataLive,
  lastCandleTime,
}: Props) {
  const [draft, setDraft] = useState(profile)
  const [savedFlash, setSavedFlash] = useState(false)
  const [splitInfoOpen, setSplitInfoOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    setDraft(profile)
    setSavedFlash(false)
    setSplitInfoOpen(false)
  }, [open, profile])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

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

  const swingPreview = useMemo(
    () => sizePreview(live.swingEquity, live.swingRiskPerTradeInr),
    [live.swingEquity, live.swingRiskPerTradeInr],
  )
  const intraPreview = useMemo(() => {
    const pctBudget =
      (Number(live.intradayEquity) * ORB_V1_RULES.riskPerTradePct) / 100
    const abs = Number(live.intradayRiskPerTradeInr)
    const budget = Math.min(
      Number.isFinite(pctBudget) ? pctBudget : Infinity,
      Number.isFinite(abs) && abs > 0 ? abs : Infinity,
    )
    return sizePreview(live.intradayEquity, String(budget))
  }, [live.intradayEquity, live.intradayRiskPerTradeInr])

  function patch(partial: Partial<RiskProfile>) {
    setDraft((prev) => ({ ...prev, ...partial }))
  }

  function handleApplyTradepilotSplit() {
    const total = Number(draft.totalEquity)
    if (!Number.isFinite(total) || total <= 0) return
    setDraft(applyTradepilotSplit(draft))
  }

  function handleClearSplit() {
    patch({ allocationMode: 'manual' })
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
    if (Number(next.intradayRiskPerTradeInr) <= 0) return
    onProfileChange(next)
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
        <form className="capital-risk-card capital-risk-card-scroll" onSubmit={handleSave}>
          <div className="capital-risk-modal-head">
            <h1 id="capital-risk-title">Capital & risk</h1>
            <button type="button" className="ghost-btn capital-risk-close" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
          <p className="field-hint capital-risk-rec">
            Enter your total capital. Use <strong>TradePilot Split Strategy</strong> only if you want an
            automatic 70% Swing / 20% Intraday / 10% Reserve split. Otherwise set desk amounts manually.
            Risk is capped in ₹ — reserve is never used for sizing.
          </p>

          <div className="capital-risk-fields capital-risk-total-row">
            <label className="field capital-risk-field" htmlFor="capital-total">
              <span>Total trading capital</span>
              <input
                id="capital-total"
                type="number"
                min="0"
                step="1"
                value={draft.totalEquity}
                onChange={(e) => {
                  const totalEquity = e.target.value
                  if (draft.allocationMode === 'tradepilot_split') {
                    setDraft(applyTradepilotSplit({ ...draft, totalEquity }))
                  } else {
                    patch({ totalEquity, allocationMode: 'manual' })
                  }
                }}
                autoFocus
              />
              <strong className="capital-risk-display">{formatInr(Number(live.totalEquity))}</strong>
            </label>
            <div className="capital-risk-strategy-col">
              <div className="capital-risk-strategy-row">
                <button
                  type="button"
                  className={`secondary-button${splitActive ? ' is-active-strategy' : ''}`}
                  onClick={handleApplyTradepilotSplit}
                >
                  TradePilot Split Strategy (70/20/10)
                </button>
                <button
                  type="button"
                  className={`capital-risk-info-btn${splitInfoOpen ? ' is-open' : ''}`}
                  aria-expanded={splitInfoOpen}
                  aria-controls="tradepilot-split-info"
                  title="About TradePilot Split"
                  onClick={() => setSplitInfoOpen((v) => !v)}
                >
                  <span aria-hidden="true">i</span>
                  <span className="sr-only">About TradePilot Split</span>
                </button>
              </div>
              {splitInfoOpen ? (
                <div id="tradepilot-split-info" className="capital-risk-split-info" role="note">
                  <p>
                    <strong>How it works:</strong> your total capital is split into{' '}
                    <strong>70% Swing</strong>, <strong>20% Intraday</strong>, and{' '}
                    <strong>10% Reserve</strong>. Changing total keeps the same ratios.
                  </p>
                  <p>
                    <strong>Why use it:</strong> Swing needs more capital for multi-day holds; Intraday
                    uses a smaller sleeve for same-day risk; Reserve stays untouchable so one bad day
                    cannot wipe the whole account. Desks size independently — losses in one do not
                    borrow from another.
                  </p>
                </div>
              ) : null}
              {splitActive ? (
                <button type="button" className="ghost-btn" onClick={handleClearSplit}>
                  Clear split · edit desks manually
                </button>
              ) : (
                <p className="field-hint">Optional — applies 70/20/10 to the total above.</p>
              )}
            </div>
          </div>

          {splitActive ? (
            <div className="capital-risk-fields capital-risk-fields-triple">
              <div className="field capital-risk-field">
                <span>Swing 70%</span>
                <strong className="capital-risk-display">{formatInr(Number(live.swingEquity))}</strong>
              </div>
              <div className="field capital-risk-field">
                <span>Intraday 20%</span>
                <strong className="capital-risk-display">{formatInr(Number(live.intradayEquity))}</strong>
              </div>
              <div className="field capital-risk-field">
                <span>Reserve 10%</span>
                <strong className="capital-risk-display">{formatInr(Number(live.reserveEquity))}</strong>
              </div>
            </div>
          ) : (
            <div className="capital-risk-fields capital-risk-fields-triple">
              <label className="field capital-risk-field" htmlFor="capital-swing-amt">
                <span>Swing capital</span>
                <input
                  id="capital-swing-amt"
                  type="number"
                  min="0"
                  step="1"
                  value={draft.swingEquity}
                  onChange={(e) => patch({ swingEquity: e.target.value, allocationMode: 'manual' })}
                />
                <strong className="capital-risk-display">{formatInr(Number(live.swingEquity))}</strong>
              </label>
              <label className="field capital-risk-field" htmlFor="capital-intra-amt">
                <span>Intraday capital</span>
                <input
                  id="capital-intra-amt"
                  type="number"
                  min="0"
                  step="1"
                  value={draft.intradayEquity}
                  onChange={(e) =>
                    patch({ intradayEquity: e.target.value, allocationMode: 'manual' })
                  }
                />
                <strong className="capital-risk-display">{formatInr(Number(live.intradayEquity))}</strong>
              </label>
              <label className="field capital-risk-field" htmlFor="capital-reserve-amt">
                <span>Reserve capital</span>
                <input
                  id="capital-reserve-amt"
                  type="number"
                  min="0"
                  step="1"
                  value={draft.reserveEquity}
                  onChange={(e) =>
                    patch({ reserveEquity: e.target.value, allocationMode: 'manual' })
                  }
                />
                <strong className="capital-risk-display">{formatInr(Number(live.reserveEquity))}</strong>
              </label>
            </div>
          )}

          <div className="capital-risk-limits" aria-label="Three risk limits">
            <div className="capital-risk-limit-card">
              <h3>1. Capital limit</h3>
              <p>
                Swing {formatInr(Number(live.swingEquity))} · Intraday{' '}
                {formatInr(Number(live.intradayEquity))} · Reserve{' '}
                {formatInr(Number(live.reserveEquity))} (untouchable)
                {splitActive ? ' · TradePilot split active' : ' · Manual desks'}{' '}
                <button
                  type="button"
                  className="capital-risk-info-btn capital-risk-info-btn-inline"
                  aria-expanded={splitInfoOpen}
                  aria-controls="tradepilot-split-info"
                  title="About TradePilot Split"
                  onClick={() => setSplitInfoOpen((v) => !v)}
                >
                  <span aria-hidden="true">i</span>
                  <span className="sr-only">About TradePilot Split</span>
                </button>
              </p>
            </div>
            <div className="capital-risk-limit-card">
              <h3>2. Per-trade risk</h3>
              <div className="capital-risk-fields capital-risk-fields-dual">
                <label className="field capital-risk-field" htmlFor="swing-risk-inr">
                  <span>Swing max ₹/trade</span>
                  <input
                    id="swing-risk-inr"
                    type="number"
                    min="1"
                    step="1"
                    value={draft.swingRiskPerTradeInr}
                    onChange={(e) => patch({ swingRiskPerTradeInr: e.target.value })}
                  />
                </label>
                <label className="field capital-risk-field" htmlFor="intra-risk-inr">
                  <span>Intraday max ₹/trade</span>
                  <input
                    id="intra-risk-inr"
                    type="number"
                    min="1"
                    step="1"
                    value={draft.intradayRiskPerTradeInr}
                    onChange={(e) => patch({ intradayRiskPerTradeInr: e.target.value })}
                  />
                </label>
              </div>
              <p className="field-hint">
                Swing ≈ {live.riskPercent}% of swing bucket. Intraday uses min(ORB{' '}
                {ORB_V1_RULES.riskPerTradePct}%, your ₹ cap).
              </p>
            </div>
            <div className="capital-risk-limit-card">
              <h3>3. Portfolio risk</h3>
              <div className="capital-risk-fields capital-risk-fields-triple">
                <label className="field capital-risk-field" htmlFor="swing-open-risk">
                  <span>Swing open risk ₹</span>
                  <input
                    id="swing-open-risk"
                    type="number"
                    min="1"
                    step="1"
                    value={draft.swingMaxOpenRiskInr}
                    onChange={(e) => patch({ swingMaxOpenRiskInr: e.target.value })}
                  />
                </label>
                <label className="field capital-risk-field" htmlFor="intra-open-risk">
                  <span>Intraday open risk ₹</span>
                  <input
                    id="intra-open-risk"
                    type="number"
                    min="1"
                    step="1"
                    value={draft.intradayMaxOpenRiskInr}
                    onChange={(e) => patch({ intradayMaxOpenRiskInr: e.target.value })}
                  />
                </label>
                <label className="field capital-risk-field" htmlFor="intra-daily-loss">
                  <span>Intraday daily loss ₹</span>
                  <input
                    id="intra-daily-loss"
                    type="number"
                    min="1"
                    step="1"
                    value={draft.intradayDailyLossInr}
                    onChange={(e) => patch({ intradayDailyLossInr: e.target.value })}
                  />
                </label>
              </div>
            </div>
          </div>

          <div className="capital-risk-example" role="status">
            <p>
              Swing example: {EXAMPLE.symbol} entry {formatInrExact(EXAMPLE.entry)} stop{' '}
              {formatInrExact(EXAMPLE.stop)}
              {swingPreview
                ? ` → ${swingPreview.qty.toLocaleString('en-IN')} shares · ${formatInrExact(swingPreview.atRisk)} at risk.`
                : ' — enter valid swing capital & risk ₹.'}
            </p>
            <p>
              Intraday example (min of ORB % and your ₹ cap)
              {intraPreview
                ? ` → ${intraPreview.qty.toLocaleString('en-IN')} shares · ${formatInrExact(intraPreview.atRisk)} at risk.`
                : ' — enter valid intraday capital & risk ₹.'}
            </p>
            <p className="field-hint">
              Saved desks drive Find Setups, Intraday board, and Practice wallets. Wallets update on every
              closed trade.
            </p>
          </div>

          <div className="capital-risk-sticky-actions">
            <button type="submit" className="primary-button">
              Save allocation
            </button>
            <button type="button" className="secondary-button" onClick={onClose}>
              Close
            </button>
            <p className="capital-risk-note">Engine owns Entry/SL — allocation only sizes qty per desk.</p>
            {savedFlash ? <span className="capital-risk-saved">Saved — applied to sizing & practice</span> : null}
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
