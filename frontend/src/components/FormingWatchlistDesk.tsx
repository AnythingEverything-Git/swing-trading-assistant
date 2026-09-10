import { useEffect, useMemo, useState } from 'react'
import type { FormingSetup, OpportunityScanResponse } from '../scan/types'
import type { DirectionFilter, FormingControls, FormingStageFilter } from '../scan/resultControls'
import { formingStageLabel, directionLabel } from '../terminology'
import { LiveValue } from './LiveValue'

export const DEFAULT_FORMING_PAGE_SIZE = 20
export const FORMING_PAGE_SIZE_OPTIONS = [10, 20, 30, 50] as const

export function formingProgressPercent(item: FormingSetup): number {
  const elapsed = Math.max(0, Number(item.bars_elapsed) || 0)
  const remaining = Math.max(0, Number(item.bars_remaining) || 0)
  const total = elapsed + remaining
  if (total > 0) {
    return Math.max(5, Math.min(95, Math.round((100 * elapsed) / total)))
  }
  if (item.stage === 'AWAITING_CONFIRMATION') return 75
  if (item.stage === 'AWAITING_RETEST') return 45
  return 30
}

export function formingWhyWaiting(item: FormingSetup): string {
  if (item.stage === 'AWAITING_RETEST') return 'Retest forming'
  if (item.stage === 'AWAITING_CONFIRMATION') return 'Confirmation due'
  const text = (item.narrative || item.reason || '').trim()
  if (!text) return 'Breakout pending'
  return text.length > 64 ? `${text.slice(0, 61)}…` : text
}

export function whyWatchingChecklist(item: FormingSetup | null): { ok: boolean; label: string }[] {
  if (!item) {
    return [
      { ok: false, label: 'Select a forming name to see what’s done' },
      { ok: false, label: 'Breakout happened — retest or confirmation still open' },
      { ok: false, label: 'No Entry / Stop / Target until confirmed' },
    ]
  }
  const waitingRetest = item.stage === 'AWAITING_RETEST'
  const waitingConfirm = item.stage === 'AWAITING_CONFIRMATION'
  return [
    {
      ok: true,
      label: item.structure_label
        ? `Structure: ${item.structure_label}`
        : 'Breakout step already seen',
    },
    {
      ok: !waitingRetest,
      label: waitingRetest
        ? 'Still waiting for retest of the broken level'
        : waitingConfirm
          ? 'Retest done — waiting for final confirmation bar'
          : formingStageLabel(item.stage),
    },
    {
      ok: false,
      label: 'Not eligible yet — no buy/sell price, safety exit, or profit goal',
    },
  ]
}

type Props = {
  scanResult: OpportunityScanResponse
  rows: FormingSetup[]
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
  onOpenDetail: (symbol: string) => void
  formingControls: FormingControls
  onFormingControlsChange: (next: FormingControls) => void
  onResetFilters: () => void
  formatPrice: (value: string | number | null | undefined) => string
  formatNumber: (value: string | number | null | undefined, digits?: number) => string
  formatPercent: (value: string | number | null | undefined) => string
  formatDateTime: (value: string | null | undefined) => string
  coveragePct: number | null
  dataAsOf: string | null
  onRefresh: () => void
  refreshing: boolean
  /** How many forming rows to show before See more (default 20). */
  pageSize?: number
}

export function FormingWatchlistDesk({
  scanResult,
  rows,
  selectedSymbol,
  onSelect,
  onOpenDetail,
  formingControls,
  onFormingControlsChange,
  onResetFilters,
  formatPrice,
  formatNumber,
  formatPercent,
  formatDateTime,
  coveragePct,
  dataAsOf,
  onRefresh,
  refreshing,
  pageSize: pageSizeProp = DEFAULT_FORMING_PAGE_SIZE,
}: Props) {
  const [pageSize, setPageSize] = useState(() =>
    Math.max(1, Math.min(100, Number(pageSizeProp) || DEFAULT_FORMING_PAGE_SIZE)),
  )
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    setPageSize(Math.max(1, Math.min(100, Number(pageSizeProp) || DEFAULT_FORMING_PAGE_SIZE)))
  }, [pageSizeProp])

  useEffect(() => {
    setShowAll(false)
  }, [formingControls.direction, formingControls.stage, formingControls.sortBy, formingControls.sortDir, rows.length])

  const visibleRows = useMemo(() => {
    if (showAll || rows.length <= pageSize) return rows
    return rows.slice(0, pageSize)
  }, [rows, pageSize, showAll])

  const canPaginate = rows.length > pageSize
  const hiddenCount = Math.max(0, rows.length - pageSize)

  const selected =
    rows.find((item) => item.symbol === selectedSymbol) ||
    scanResult.forming?.find((item) => item.symbol === selectedSymbol) ||
    visibleRows[0] ||
    null

  const why = useMemo(() => whyWatchingChecklist(selected), [selected])
  const total = scanResult.forming?.length ?? 0

  return (
    <section className="forming-watchlist" aria-label="Forming watchlist">
      <header className="forming-watchlist-head">
        <div>
          <h2>Forming watchlist</h2>
          <p className="field-hint">
            Near setups not yet confirmed.
            {rows.length > 0
              ? ` Showing ${visibleRows.length} of ${rows.length}${total > rows.length ? ` (filtered from ${total})` : ''}.`
              : null}
          </p>
        </div>
        <div className="forming-watchlist-toolbar">
          <label className="find-sort">
            <span>Show</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setShowAll(false)
              }}
              aria-label="Rows per page"
            >
              {FORMING_PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size} at a time
                </option>
              ))}
            </select>
          </label>
          <label className="find-sort">
            <span>Type</span>
            <select
              value={formingControls.direction}
              onChange={(e) =>
                onFormingControlsChange({
                  ...formingControls,
                  direction: e.target.value as DirectionFilter,
                })
              }
            >
              <option value="ALL">All</option>
              <option value="LONG">Buy</option>
              <option value="SHORT">Sell short</option>
            </select>
          </label>
          <label className="find-sort">
            <span>Stage</span>
            <select
              value={formingControls.stage}
              onChange={(e) =>
                onFormingControlsChange({
                  ...formingControls,
                  stage: e.target.value as FormingStageFilter,
                })
              }
            >
              <option value="ALL">All stages</option>
              <option value="AWAITING_RETEST">Waiting retest</option>
              <option value="AWAITING_CONFIRMATION">Waiting confirmation</option>
            </select>
          </label>
          <button type="button" className="secondary-button find-tool-btn" onClick={onResetFilters}>
            Reset
          </button>
        </div>
      </header>

      <div className="forming-watchlist-layout">
        <div className="forming-watchlist-main">
          {rows.length === 0 ? (
            <div className="empty-state">
              <strong>{total === 0 ? 'No forming setups' : 'No matches for these filters'}</strong>
              <span>
                {total === 0
                  ? 'Run Find setups again after the next session, or loosen filters.'
                  : 'Widen trade type or stage, then try again.'}
              </span>
            </div>
          ) : (
            <div className="forming-table-wrap">
              <table className="forming-table">
                <thead>
                  <tr>
                    <th scope="col" className="num">
                      Rank
                    </th>
                    <th scope="col">Stock</th>
                    <th scope="col">Stage</th>
                    <th scope="col">Progress</th>
                    <th scope="col">Why waiting</th>
                    <th scope="col" className="action" aria-label="Open" />
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((item, index) => {
                    const progress = formingProgressPercent(item)
                    const active = selected?.symbol === item.symbol
                    const isShort = (item.direction ?? 'LONG') === 'SHORT'
                    return (
                      <tr
                        key={item.symbol}
                        className={active ? 'is-selected' : ''}
                        onClick={() => onSelect(item.symbol)}
                      >
                        <td className="num">{index + 1}</td>
                        <td>
                          <div className="forming-sym">
                            <strong>{item.symbol}</strong>
                            <span className={`direction-pill compact ${isShort ? 'short' : 'long'}`}>
                              {directionLabel(item.direction)}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className="forming-stage-pill">Forming</span>
                          <span className="forming-stage-detail">{formingStageLabel(item.stage)}</span>
                        </td>
                        <td>
                          <div className="forming-progress" title={`${progress}% of path complete`}>
                            <div className="forming-progress-track" aria-hidden="true">
                              <i style={{ width: `${progress}%` }} />
                            </div>
                            <span>{progress}%</span>
                          </div>
                          <span className="forming-progress-meta">
                            {item.bars_remaining} day{item.bars_remaining === 1 ? '' : 's'} left · Live{' '}
                            <LiveValue
                              value={item.current_price}
                              formatted={formatPrice(item.current_price)}
                            />{' '}
                            <em className={Number(item.current_price_change_percent) >= 0 ? 'up' : 'down'}>
                              {formatPercent(item.current_price_change_percent)}
                            </em>
                          </span>
                        </td>
                        <td className="why">{formingWhyWaiting(item)}</td>
                        <td className="action">
                          <button
                            type="button"
                            className="ghost-btn find-row-open"
                            aria-label={`Open ${item.symbol}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              onOpenDetail(item.symbol)
                            }}
                          >
                            <span className="find-ico find-ico-chevron-right" aria-hidden="true" />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="forming-table-foot">
                <p>Not eligible yet — watch only.</p>
                {canPaginate ? (
                  <div className="forming-pager">
                    {showAll ? (
                      <button
                        type="button"
                        className="link-button forming-pager-btn"
                        onClick={() => setShowAll(false)}
                      >
                        See less
                        <span className="find-ico find-ico-chevron-up" aria-hidden="true" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="link-button forming-pager-btn"
                        onClick={() => setShowAll(true)}
                      >
                        See more ({hiddenCount} more)
                        <span className="find-ico find-ico-chevron-down" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>

        <aside className="forming-watchlist-rail">
          <section className="find-why-panel">
            <h3>
              <span className="find-ico find-ico-check-badge" aria-hidden="true" />
              Why watching?
            </h3>
            <ul className="find-why-list">
              {why.map((item) => (
                <li key={item.label} className={item.ok ? 'ok' : 'warn'}>
                  <span className={`find-why-mark ${item.ok ? 'is-ok' : ''}`} aria-hidden="true" />
                  {item.label}
                </li>
              ))}
            </ul>
            {selected ? (
              <p className="field-hint find-live">
                Key level {formatPrice(selected.resistance)} · ATR {formatNumber(selected.atr_value, 2)}
              </p>
            ) : null}
          </section>
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
