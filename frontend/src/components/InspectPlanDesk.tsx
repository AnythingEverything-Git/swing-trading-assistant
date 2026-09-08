import { useMemo } from 'react'
import type { Opportunity } from '../scan/types'
import { strategyConfidencePercent } from '../scan/resultControls'
import { directionLabel } from '../terminology'
import type { DeductionStep } from '../planDeduction'
import { PlanDeductionPanel } from './PlanDeductionPanel'
import { SetupChart, type ChartCandle } from './SetupChart'
import { LiveValue } from './LiveValue'

type Props = {
  opportunity: Opportunity
  baseUrl: string
  chartCandles: ChartCandle[]
  deductionSteps: DeductionStep[]
  formatPrice: (value: string | number | null | undefined) => string
  formatRatio: (value: string | number | null | undefined) => string
  formatDateTime: (value: string | null | undefined) => string
  coveragePct: number | null
  dataAsOf: string | null
  onClose: () => void
  onRefresh: () => void
  refreshing: boolean
  onOpenResearch: () => void
  onOpenChartEvidence: () => void
  siblings: Opportunity[]
  onSelectSibling: (symbol: string) => void
}

export function InspectPlanDesk({
  opportunity,
  baseUrl,
  chartCandles,
  deductionSteps,
  formatPrice,
  formatRatio,
  formatDateTime,
  coveragePct,
  dataAsOf,
  onClose,
  onRefresh,
  refreshing,
  onOpenResearch,
  onOpenChartEvidence,
  siblings,
  onSelectSibling,
}: Props) {
  const isShort = opportunity.candidate.direction === 'SHORT'
  const score = strategyConfidencePercent(opportunity.quality_score)
  const structureIsFloor = isShort

  const chartLevels = useMemo(
    () => ({
      resistance: structureIsFloor ? null : opportunity.evidence.resistance,
      support: structureIsFloor ? opportunity.evidence.resistance : null,
      entry: opportunity.candidate.entry_price,
      stop: opportunity.candidate.stop_loss,
      target: opportunity.candidate.target,
      breakoutIndex: opportunity.evidence.breakout_candle_index,
      retestIndex: opportunity.evidence.retest_candle_index,
      confirmationIndex: opportunity.evidence.confirmation_candle_index,
    }),
    [opportunity, structureIsFloor],
  )

  const siblingIndex = siblings.findIndex((item) => item.symbol === opportunity.symbol)
  const prev = siblingIndex > 0 ? siblings[siblingIndex - 1] : null
  const next =
    siblingIndex >= 0 && siblingIndex < siblings.length - 1 ? siblings[siblingIndex + 1] : null

  return (
    <section className="inspect-plan" aria-label={`Inspect plan ${opportunity.symbol}`}>
      <header className="inspect-plan-head">
        <div className="inspect-plan-title-block">
          <button type="button" className="link-button inspect-plan-back" onClick={onClose}>
            <span className="find-ico find-ico-arrow-left" aria-hidden="true" />
            Back
          </button>
          <h2>
            Inspect plan <span className="inspect-plan-dot" aria-hidden="true">
              ·
            </span>{' '}
            {opportunity.symbol}
          </h2>
        </div>
        <div className="inspect-plan-actions">
          {prev ? (
            <button
              type="button"
              className="ghost-btn inspect-nav-btn"
              onClick={() => onSelectSibling(prev.symbol)}
            >
              ← {prev.symbol}
            </button>
          ) : null}
          {next ? (
            <button
              type="button"
              className="ghost-btn inspect-nav-btn"
              onClick={() => onSelectSibling(next.symbol)}
            >
              {next.symbol} →
            </button>
          ) : null}
          <button type="button" className="secondary-button find-tool-btn" onClick={onOpenChartEvidence}>
            Chart evidence
          </button>
          <button type="button" className="secondary-button find-tool-btn" onClick={onOpenResearch}>
            Full research
          </button>
          <button
            type="button"
            className="ghost-btn inspect-plan-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
      </header>

      <div className="inspect-plan-grid">
        <article className="inspect-tile">
          <h3 className="inspect-tile-label">Setup details</h3>
          <div className="inspect-setup-symbol">
            <strong>{opportunity.symbol}</strong>
            <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
              {directionLabel(opportunity.candidate.direction)}
            </span>
          </div>
          <dl className="inspect-kv">
            <div>
              <dt>Entry</dt>
              <dd>{formatPrice(opportunity.candidate.entry_price)}</dd>
            </div>
            <div>
              <dt>Safety exit</dt>
              <dd>{formatPrice(opportunity.candidate.stop_loss)}</dd>
            </div>
            <div>
              <dt>Profit goal</dt>
              <dd>{formatPrice(opportunity.candidate.target)}</dd>
            </div>
            <div>
              <dt>Reward vs risk</dt>
              <dd>{formatRatio(opportunity.candidate.risk_reward_ratio)}</dd>
            </div>
            <div>
              <dt>Shares</dt>
              <dd>{opportunity.quantity ?? '—'}</dd>
            </div>
            <div>
              <dt>Strategy confidence</dt>
              <dd title="Rules-based setup quality (0–100%), not a predicted win rate">
                {score != null ? `${Math.round(score)}%` : '—'}
              </dd>
            </div>
            <div>
              <dt>Live</dt>
              <dd>
                <LiveValue
                  value={opportunity.current_price}
                  formatted={formatPrice(opportunity.current_price)}
                />
              </dd>
            </div>
            {opportunity.risk_amount != null ? (
              <div>
                <dt>₹ at risk</dt>
                <dd>{formatPrice(opportunity.risk_amount)}</dd>
              </div>
            ) : null}
          </dl>
          {opportunity.invalidation ? (
            <p className="inspect-invalidation">
              <span className="find-ico find-ico-alert" aria-hidden="true" />
              Invalidation: {opportunity.invalidation}
            </p>
          ) : null}
        </article>

        <article className="inspect-tile inspect-how">
          <h3 className="inspect-tile-label">How decided</h3>
          <PlanDeductionPanel
            symbol={opportunity.symbol}
            steps={deductionSteps}
            baseUrl={baseUrl}
            compact
          />
        </article>

        <article className="inspect-tile inspect-price">
          <h3 className="inspect-tile-label">Price action</h3>
          <div className="inspect-chart-body">
            <SetupChart candles={chartCandles} levels={chartLevels} height={380} variant="inspect" />
          </div>
          <ul className="inspect-chart-legend" aria-label="Plan levels on chart">
            <li>
              <span className="inspect-legend-dot is-entry" aria-hidden="true" />
              Entry
            </li>
            <li>
              <span className="inspect-legend-dot is-stop" aria-hidden="true" />
              Stop
            </li>
            <li>
              <span className="inspect-legend-dot is-target" aria-hidden="true" />
              Target
            </li>
          </ul>
          <button type="button" className="link-button chart-evidence-link" onClick={onOpenChartEvidence}>
            Open full chart evidence
            <span className="find-ico find-ico-arrow" aria-hidden="true" />
          </button>
        </article>
      </div>

      <footer className="inspect-plan-footer">
        <div className="find-coverage">
          <span>Data coverage</span>
          <div className="find-coverage-bar" aria-hidden="true">
            <i style={{ width: `${Math.max(0, Math.min(100, coveragePct ?? 0))}%` }} />
          </div>
          <strong>{coveragePct != null ? `${Math.round(coveragePct)}%` : '—'}</strong>
        </div>
        <p className="find-footer-disclaimer">Not financial advice. Trading involves risk.</p>
        <div className="find-footer-right">
          <span className="find-footer-asof">
            Data as of {dataAsOf ? formatDateTime(dataAsOf) : '—'}
          </span>
          <button
            type="button"
            className="secondary-button find-tool-btn"
            disabled={refreshing}
            onClick={onRefresh}
          >
            Refresh
          </button>
        </div>
      </footer>
    </section>
  )
}
