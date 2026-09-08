import { useMemo } from 'react'
import type { Opportunity } from '../scan/types'
import { directionLabel } from '../terminology'
import { SetupChart, type ChartCandle } from './SetupChart'

type Props = {
  opportunity: Opportunity
  chartCandles: ChartCandle[]
  formatPrice: (value: string | number | null | undefined) => string
  formatNumber: (value: string | number | null | undefined, digits?: number) => string
  formatVolume: (value: string | number | null | undefined) => string
  formatDateTime: (value: string | null | undefined) => string
  formatBarRef: (index: number, time: string) => { bar: string; when: string }
  coveragePct: number | null
  dataAsOf: string | null
  onBack: () => void
  onClose: () => void
  onRefresh: () => void
  refreshing: boolean
  onOpenResearch: () => void
}

function ratioLabel(num: number | null, den: number | null): string {
  if (num == null || den == null || den <= 0 || !Number.isFinite(num) || !Number.isFinite(den)) return '—'
  return `${(num / den).toFixed(2)}×`
}

export function ChartEvidenceDesk({
  opportunity,
  chartCandles,
  formatPrice,
  formatNumber,
  formatVolume,
  formatDateTime,
  formatBarRef,
  coveragePct,
  dataAsOf,
  onBack,
  onClose,
  onRefresh,
  refreshing,
  onOpenResearch,
}: Props) {
  const isShort = opportunity.candidate.direction === 'SHORT'
  const structureIsFloor = isShort
  const structureWord = structureIsFloor ? 'Floor (support)' : 'Ceiling (resistance)'
  const ev = opportunity.evidence

  const chartLevels = useMemo(
    () => ({
      resistance: structureIsFloor ? null : ev.resistance,
      support: structureIsFloor ? ev.resistance : null,
      entry: opportunity.candidate.entry_price,
      stop: opportunity.candidate.stop_loss,
      target: opportunity.candidate.target,
      breakoutIndex: ev.breakout_candle_index,
      retestIndex: ev.retest_candle_index,
      confirmationIndex: ev.confirmation_candle_index,
    }),
    [opportunity, structureIsFloor, ev],
  )

  const atr = Number(ev.atr_value)
  const volumeSma = Number(ev.volume_sma_value)
  const breakoutVol = ev.breakout_volume != null ? Number(ev.breakout_volume) : null
  const confirmVol = ev.confirmation_volume != null ? Number(ev.confirmation_volume) : null
  const riskPerShare = Number(opportunity.candidate.risk_per_share)
  const atrRisk =
    Number.isFinite(atr) && atr > 0 && Number.isFinite(riskPerShare)
      ? `${(riskPerShare / atr).toFixed(2)}× ATR`
      : '—'

  const breakoutRef = formatBarRef(ev.breakout_candle_index, ev.breakout_candle_time)
  const retestRef = formatBarRef(ev.retest_candle_index, ev.retest_candle_time)
  const confirmRef = formatBarRef(ev.confirmation_candle_index, ev.confirmation_candle_time)

  const volOk =
    (breakoutVol != null && volumeSma > 0 && breakoutVol >= volumeSma) ||
    (confirmVol != null && volumeSma > 0 && confirmVol >= volumeSma * 0.8)

  return (
    <section className="chart-evidence" aria-label={`Chart evidence ${opportunity.symbol}`}>
      <header className="inspect-plan-head">
        <div className="inspect-plan-title-block">
          <button type="button" className="link-button inspect-plan-back" onClick={onBack}>
            <span className="find-ico find-ico-arrow-left" aria-hidden="true" />
            Back to plan
          </button>
          <h2>
            Chart evidence <span className="inspect-plan-dot" aria-hidden="true">
              ·
            </span>{' '}
            {opportunity.symbol}
          </h2>
        </div>
        <div className="inspect-plan-actions">
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

      <div className="chart-evidence-grid">
        <article className="inspect-tile chart-evidence-main">
          <div className="chart-evidence-main-head">
            <h3 className="inspect-tile-label">Setup chart · {opportunity.symbol}</h3>
            <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
              {directionLabel(opportunity.candidate.direction)}
            </span>
          </div>
          <div className="chart-evidence-canvas">
            <SetupChart candles={chartCandles} levels={chartLevels} height={440} variant="evidence" />
          </div>
          <ul className="inspect-chart-legend chart-evidence-legend" aria-label="Chart overlays">
            <li>
              <span className="inspect-legend-dot is-entry" aria-hidden="true" />
              Entry {formatPrice(opportunity.candidate.entry_price)}
            </li>
            <li>
              <span className="inspect-legend-dot is-stop" aria-hidden="true" />
              Stop {formatPrice(opportunity.candidate.stop_loss)}
            </li>
            <li>
              <span className="inspect-legend-dot is-target" aria-hidden="true" />
              Target {formatPrice(opportunity.candidate.target)}
            </li>
            <li>
              <span className="chart-evidence-marker is-b" aria-hidden="true">
                B
              </span>
              Breakout
            </li>
            <li>
              <span className="chart-evidence-marker is-r" aria-hidden="true">
                R
              </span>
              Retest
            </li>
            <li>
              <span className="chart-evidence-marker is-c" aria-hidden="true">
                C
              </span>
              Confirmation
            </li>
          </ul>
        </article>

        <aside className="inspect-tile chart-evidence-notes">
          <h3 className="inspect-tile-label">Structure notes</h3>
          <ul className="chart-evidence-note-list">
            <li className="chart-evidence-note">
              <span className="chart-evidence-note-ico find-ico find-ico-pulse" aria-hidden="true" />
              <div>
                <strong>ATR context</strong>
                <p>
                  ATR(14) {formatNumber(ev.atr_value, 2)} · risk per share{' '}
                  {formatPrice(opportunity.candidate.risk_per_share)} ({atrRisk})
                </p>
              </div>
            </li>
            <li className={`chart-evidence-note ${volOk ? 'is-ok' : 'is-warn'}`}>
              <span
                className={`chart-evidence-note-ico find-ico ${volOk ? 'find-ico-check-badge' : 'find-ico-alert'}`}
                aria-hidden="true"
              />
              <div>
                <strong>Volume confirmation</strong>
                <p>
                  Breakout {formatVolume(breakoutVol)} ({ratioLabel(breakoutVol, volumeSma)} vs SMA) · Confirm{' '}
                  {formatVolume(confirmVol)} ({ratioLabel(confirmVol, volumeSma)} vs SMA)
                </p>
              </div>
            </li>
            <li className="chart-evidence-note">
              <span className="chart-evidence-note-ico find-ico find-ico-grid" aria-hidden="true" />
              <div>
                <strong>{structureWord}</strong>
                <p>
                  {formatPrice(ev.resistance)} · Retest{' '}
                  {formatPrice(ev.retest_low)} · Decision: {ev.decision || 'confirmed'}
                </p>
              </div>
            </li>
            <li className="chart-evidence-note">
              <span className="chart-evidence-note-ico find-ico find-ico-star" aria-hidden="true" />
              <div>
                <strong>Evidence bars</strong>
                <p>
                  B {breakoutRef.bar} ({breakoutRef.when}) · R {retestRef.bar} ({retestRef.when}) · C{' '}
                  {confirmRef.bar} ({confirmRef.when})
                </p>
              </div>
            </li>
          </ul>
          {opportunity.invalidation ? (
            <p className="inspect-invalidation">
              <span className="find-ico find-ico-alert" aria-hidden="true" />
              Invalidation: {opportunity.invalidation}
            </p>
          ) : null}
          {opportunity.narrative ? (
            <p className="chart-evidence-narrative">{opportunity.narrative}</p>
          ) : null}
        </aside>
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
