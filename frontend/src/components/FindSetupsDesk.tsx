import { useMemo, useState, type ReactNode } from 'react'
import type { Opportunity, OpportunityScanResponse } from '../scan/types'
import { strategyConfidencePercent } from '../scan/resultControls'
import { directionLabel } from '../terminology'
import type { UniverseFilterState } from './FilterBuilder'
import { LiveValue } from './LiveValue'
import { AutoRefreshBar } from './AutoRefreshBar'
import { InvalidationPanel } from './InvalidationPanel'

export function countActiveFilters(f: UniverseFilterState): number {
  let n = 0
  if (f.asset_class !== 'ALL') n += 1
  if (f.min_price) n += 1
  if (f.max_price) n += 1
  if (f.min_adv_inr) n += 1
  if (f.sectors.length) n += 1
  if (f.exclude_surveillance) n += 1
  if (f.exclude_corporate_actions) n += 1
  if (f.direction !== 'ALL') n += 1
  return n
}

type WhyItem = { ok: boolean; label: string }

export function whyEligibleChecklist(item: Opportunity | null): WhyItem[] {
  if (!item) {
    return [
      { ok: false, label: 'Select a setup to see why it is eligible' },
      { ok: false, label: 'Risk/reward from engine levels' },
      { ok: false, label: 'Volume confirmation on breakout/retest' },
    ]
  }
  const rr = Number(item.candidate.risk_reward_ratio)
  const confVol = item.evidence.confirmation_volume
  const breakVol = item.evidence.breakout_volume
  const volOk = (confVol != null && confVol > 0) || (breakVol != null && breakVol > 0)
  const structureOk = Boolean(item.evidence.decision || item.evidence.structure_label)
  return [
    {
      ok: structureOk,
      label: item.evidence.structure_label
        ? `Structure: ${item.evidence.structure_label}`
        : 'Breakout / retest structure present',
    },
    {
      ok: Number.isFinite(rr) && rr >= 2,
      label: Number.isFinite(rr) ? `Risk/reward ${rr.toFixed(2)}:1` : 'Risk/reward from engine levels',
    },
    {
      ok: volOk,
      label: volOk ? 'Volume confirmation on key bars' : 'Volume confirmation weak or missing',
    },
  ]
}

type CriteriaProps = {
  universeLabel: string
  filterSummary: string
  filterCount: number
  riskPercent: string
  onRiskChange: (value: string) => void
  onOpenUniverse: () => void
  onOpenFilters: () => void
  onFindSetups: () => void
  loading: boolean
  progress: string
  collapsed: boolean
  onToggleCollapsed: () => void
  showCollapse: boolean
  advanced: ReactNode
}

export function FindSetupsCriteriaBar({
  universeLabel,
  filterSummary,
  filterCount,
  riskPercent,
  onRiskChange,
  onOpenUniverse,
  onOpenFilters,
  onFindSetups,
  loading,
  progress,
  collapsed,
  onToggleCollapsed,
  showCollapse,
  advanced,
}: CriteriaProps) {
  const filterLabel = filterCount > 0 ? `${filterCount} filters active` : filterSummary

  return (
    <section className="find-criteria" aria-label="Scan criteria">
      <div className="find-criteria-head">
        <h2>
          <span className="find-ico find-ico-sliders" aria-hidden="true" />
          Criteria
        </h2>
        {showCollapse ? (
          <button type="button" className="link-button find-criteria-toggle" onClick={onToggleCollapsed}>
            {collapsed ? 'Show' : 'Hide'}
            <span className={`find-ico ${collapsed ? 'find-ico-chevron-down' : 'find-ico-chevron-up'}`} aria-hidden="true" />
          </button>
        ) : null}
      </div>

      {collapsed ? (
        <div className="find-criteria-summary">
          <button type="button" className="find-summary-chip" onClick={onOpenUniverse}>
            <span className="find-ico find-ico-globe" aria-hidden="true" />
            {universeLabel}
          </button>
          <button type="button" className="find-summary-chip" onClick={onOpenFilters}>
            <span className="find-ico find-ico-filter" aria-hidden="true" />
            {filterLabel}
          </button>
          <span className="find-summary-chip is-static">
            <span className="find-ico find-ico-risk" aria-hidden="true" />
            Risk {riskPercent}%
          </span>
          <button
            type="button"
            className="primary-button find-setups-btn find-setups-btn-compact"
            disabled={loading}
            onClick={onFindSetups}
          >
            <span className="find-ico find-ico-search" aria-hidden="true" />
            {loading ? progress || 'Scanning…' : 'Find setups'}
          </button>
        </div>
      ) : (
        <>
          <div className="find-criteria-bar">
            <button type="button" className="find-criteria-field" onClick={onOpenUniverse}>
              <span>
                <span className="find-ico find-ico-globe" aria-hidden="true" />
                Universe
              </span>
              <strong>{universeLabel}</strong>
            </button>
            <button type="button" className="find-criteria-field" onClick={onOpenFilters}>
              <span>
                <span className="find-ico find-ico-filter" aria-hidden="true" />
                Filters
              </span>
              <strong>{filterLabel}</strong>
            </button>
            <label className="find-criteria-field find-criteria-risk">
              <span>
                <span className="find-ico find-ico-risk" aria-hidden="true" />
                Risk percent
              </span>
              <div className="find-risk-row">
                <input
                  type="number"
                  min="0.1"
                  max="100"
                  step="0.01"
                  value={riskPercent}
                  onChange={(e) => onRiskChange(e.target.value)}
                />
                <em>%</em>
              </div>
            </label>
            <button
              type="button"
              className="primary-button find-setups-btn"
              disabled={loading}
              onClick={onFindSetups}
            >
              <span className="find-ico find-ico-search" aria-hidden="true" />
              {loading ? progress || 'Scanning…' : 'Find setups'}
            </button>
          </div>
          {advanced}
        </>
      )}
    </section>
  )
}

type ResultsProps = {
  scanResult: OpportunityScanResponse
  topIdeas: Opportunity[]
  rows: Opportunity[]
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
  onOpenDetail: (symbol: string) => void
  onViewAll: () => void
  showAll: boolean
  formatPrice: (value: string | number | null | undefined) => string
  sortLabel: string
  onSortChange: (value: string) => void
  coveragePct: number | null
  dataAsOf: string | null
  formatDateTime: (value: string | null | undefined) => string
  onRefresh: () => void
  refreshing: boolean
  onExportCsv: () => void
  onOpenCoverage: () => void
  autoRefresh?: {
    enabled: boolean
    onEnabledChange: (next: boolean) => void
    intervalSec: string
    onIntervalChange: (next: string) => void
    secondsLeft: number | null
    paused: boolean
    pauseReason: string | null
    refreshing: boolean
    disabled?: boolean
  }
}

export function FindSetupsResultsLayout({
  scanResult,
  topIdeas,
  rows,
  selectedSymbol,
  onSelect,
  onOpenDetail,
  onViewAll,
  showAll,
  formatPrice,
  sortLabel,
  onSortChange,
  coveragePct,
  dataAsOf,
  formatDateTime,
  onRefresh,
  refreshing,
  onExportCsv,
  onOpenCoverage,
  autoRefresh,
}: ResultsProps) {
  const selected =
    rows.find((r) => r.symbol === selectedSymbol) ||
    topIdeas.find((r) => r.symbol === selectedSymbol) ||
    topIdeas[0] ||
    rows[0] ||
    null

  const why = useMemo(() => whyEligibleChecklist(selected), [selected])

  return (
    <div className="find-setups-layout" id="find-setups-results">
      <section className="find-top-ideas">
        <div className="find-section-head">
          <div className="find-section-title">
            <h2>
              <span className="find-ico find-ico-star" aria-hidden="true" />
              Top ideas
            </h2>
            <p className="field-hint">Based on your criteria.</p>
          </div>
          {scanResult.eligible_count > topIdeas.length ? (
            <button type="button" className="link-button find-link-with-ico" onClick={onViewAll}>
              {showAll ? 'Show top only' : 'View all setups'}
              <span className="find-ico find-ico-arrow" aria-hidden="true" />
            </button>
          ) : null}
        </div>
        {topIdeas.length === 0 ? (
          <div className="empty-state">
            <strong>No ready ideas</strong>
            <span>Loosen filters, widen dates, or open Coverage — then Find setups again.</span>
          </div>
        ) : (
          <div
            className="find-top-grid"
            style={{ ['--find-top-cols' as string]: String(Math.min(Math.max(topIdeas.length, 1), 3)) }}
          >
            {topIdeas.map((item) => {
              const isShort = item.candidate.direction === 'SHORT'
              return (
                <article
                  key={item.symbol}
                  className={`find-top-card ${selected?.symbol === item.symbol ? 'is-selected' : ''} ${
                    isShort ? 'is-short' : 'is-long'
                  }`}
                >
                  <button type="button" className="find-top-card-btn" onClick={() => onSelect(item.symbol)}>
                    <div className="find-top-card-head">
                      <strong>{item.symbol}</strong>
                      <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                        {directionLabel(item.candidate.direction)}
                      </span>
                    </div>
                    <div className="find-top-levels">
                      <div>
                        <span className="find-level-label">Entry</span>
                        <em>{formatPrice(item.candidate.entry_price)}</em>
                      </div>
                      <div>
                        <span className="find-level-label">Stop</span>
                        <em>{formatPrice(item.candidate.stop_loss)}</em>
                      </div>
                      <div>
                        <span className="find-level-label">Target</span>
                        <em>{formatPrice(item.candidate.target)}</em>
                      </div>
                    </div>
                    <p className="find-top-insight">
                      <span className="find-ico find-ico-bulb" aria-hidden="true" />
                      <span className="find-top-insight-text">
                        {item.narrative || item.quality_reason || item.evidence.decision || 'Engine-confirmed setup'}
                      </span>
                    </p>
                  </button>
                  <button
                    type="button"
                    className="link-button find-top-open find-link-with-ico"
                    onClick={() => onOpenDetail(item.symbol)}
                  >
                    Open plan
                    <span className="find-ico find-ico-arrow" aria-hidden="true" />
                  </button>
                </article>
              )
            })}
          </div>
        )}
      </section>

      <section className="find-why-panel">
        <h3>
          <span className="find-ico find-ico-check-badge" aria-hidden="true" />
          Why eligible?
        </h3>
        <ul className="find-why-list">
          {why.map((item) => (
            <li key={item.label} className={item.ok ? 'ok' : 'warn'}>
              <span className={`find-why-mark ${item.ok ? 'is-ok' : ''}`} aria-hidden="true" />
              {item.label}
            </li>
          ))}
        </ul>
        {selected?.invalidation ? (
          <p className="field-hint find-invalidation">
            <span className="find-ico find-ico-alert" aria-hidden="true" />
            Invalidation: {selected.invalidation}
          </p>
        ) : null}
        <InvalidationPanel
          className="find-invalidation-panel"
          facts={
            selected
              ? {
                  symbol: selected.symbol,
                  invalidation: selected.invalidation,
                  detail: selected.quality_reason || selected.narrative,
                  checklist: selected.invalidation
                    ? [
                        selected.invalidation,
                        selected.quality_reason || 'Quality critique from engine scan',
                      ].filter(Boolean) as string[]
                    : null,
                }
              : null
          }
        />
        {selected ? (
          <p className="field-hint find-live">
            <span className="find-ico find-ico-pulse" aria-hidden="true" />
            Live{' '}
            <LiveValue
              value={selected.current_price}
              formatted={formatPrice(selected.current_price)}
            />
          </p>
        ) : null}
      </section>

      <section className="find-results">
        {autoRefresh ? (
          <AutoRefreshBar
            enabled={autoRefresh.enabled}
            onEnabledChange={autoRefresh.onEnabledChange}
            intervalSec={autoRefresh.intervalSec}
            onIntervalChange={autoRefresh.onIntervalChange}
            secondsLeft={autoRefresh.secondsLeft}
            paused={autoRefresh.paused}
            pauseReason={autoRefresh.pauseReason}
            refreshing={autoRefresh.refreshing}
            disabled={autoRefresh.disabled}
          />
        ) : null}
        <div className="find-results-head">
          <div className="find-section-title">
            <h2>Results</h2>
            <p className="field-hint">{scanResult.eligible_count} setups found</p>
          </div>
          <div className="find-results-toolbar">
            <button type="button" className="secondary-button find-tool-btn" onClick={onExportCsv}>
              <span className="find-ico find-ico-download" aria-hidden="true" />
              Export CSV
            </button>
            <label className="find-sort">
              <span>Sort</span>
              <select value={sortLabel} onChange={(e) => onSortChange(e.target.value)}>
                <option value="confidence">Score</option>
                <option value="rank">Rank</option>
                <option value="rr">Reward vs risk</option>
                <option value="symbol">Symbol</option>
              </select>
            </label>
            <button type="button" className="secondary-button find-tool-btn" onClick={onOpenCoverage}>
              <span className="find-ico find-ico-grid" aria-hidden="true" />
              Coverage
            </button>
          </div>
        </div>
        <div className="find-results-table-wrap">
          <table className="find-results-table">
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">Direction</th>
                <th scope="col" className="num">Entry</th>
                <th scope="col" className="num">Stop</th>
                <th scope="col" className="num">Target</th>
                <th scope="col" className="num">Score</th>
                <th scope="col" className="num">Qty</th>
                <th scope="col" className="action" aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="coverage-empty">
                    No setups match the current filters.
                  </td>
                </tr>
              ) : (
                rows.map((opportunity) => {
                  const isShort = opportunity.candidate.direction === 'SHORT'
                  const score = strategyConfidencePercent(opportunity.quality_score)
                  const active = selected?.symbol === opportunity.symbol
                  return (
                    <tr
                      key={opportunity.symbol}
                      className={active ? 'is-selected' : ''}
                      onClick={() => onSelect(opportunity.symbol)}
                    >
                      <td className="sym">{opportunity.symbol}</td>
                      <td>
                        <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                          {directionLabel(opportunity.candidate.direction)}
                        </span>
                      </td>
                      <td className="num">{formatPrice(opportunity.candidate.entry_price)}</td>
                      <td className="num">{formatPrice(opportunity.candidate.stop_loss)}</td>
                      <td className="num">{formatPrice(opportunity.candidate.target)}</td>
                      <td className="num">
                        <strong>{score != null ? Math.round(score) : '—'}</strong>
                      </td>
                      <td className="num">{opportunity.quantity ?? '—'}</td>
                      <td className="action">
                        <button
                          type="button"
                          className="ghost-btn find-row-open"
                          aria-label={`Open ${opportunity.symbol}`}
                          onClick={(e) => {
                            e.stopPropagation()
                            onOpenDetail(opportunity.symbol)
                          }}
                        >
                          <span className="find-ico find-ico-chevron-right" aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="find-setups-footer">
        <div className="find-coverage">
          <span className="find-ico find-ico-signal" aria-hidden="true" />
          <span>Data coverage</span>
          <div className="find-coverage-bar" aria-hidden="true">
            <i style={{ width: `${Math.max(0, Math.min(100, coveragePct ?? 0))}%` }} />
          </div>
          <strong>{coveragePct != null ? `${Math.round(coveragePct)}%` : '—'}</strong>
        </div>
        <p className="find-footer-disclaimer">Not financial advice. Trading involves risk.</p>
        <div className="find-footer-right">
          <span className="find-footer-asof">
            <span className="find-ico find-ico-clock" aria-hidden="true" />
            Data as of {dataAsOf ? formatDateTime(dataAsOf) : '—'}
          </span>
          <button
            type="button"
            className="secondary-button find-tool-btn"
            disabled={refreshing}
            onClick={onRefresh}
          >
            <span className="find-ico find-ico-refresh" aria-hidden="true" />
            Refresh
          </button>
        </div>
      </footer>
    </div>
  )
}
