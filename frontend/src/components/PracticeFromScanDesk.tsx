import { useEffect, useMemo, useState } from 'react'
import type { Opportunity, OpportunityScanResponse } from '../scan/types'
import { directionLabel, paperStatusLabel } from '../terminology'
import { SetupChart, type ChartCandle } from './SetupChart'
import { LiveValue } from './LiveValue'

export const PAPER_PRACTICE_CLAIM = 'Practice is fake money — not a brokerage order.'

type PaperTradeLite = {
  id: number
  symbol: string
  status: string
  last_mark_price?: string | number | null
  unrealized_pnl?: string | number | null
}

type Props = {
  scanResult: OpportunityScanResponse
  opportunities: Opportunity[]
  paperTrades: PaperTradeLite[]
  paperEnabled: boolean
  onEnablePaper: () => void
  baseUrl: string
  chartCandles: ChartCandle[]
  focusSymbol: string | null
  onFocusSymbol: (symbol: string) => void
  formatPrice: (value: string | number | null | undefined) => string
  formatDateTime: (value: string | null | undefined) => string
  coveragePct: number | null
  dataAsOf: string | null
  onRefresh: () => void
  refreshing: boolean
  onArmed: (message: string) => void
  onOpenBook: () => void
  onTick: () => void
  ticking: boolean
}

function practiceStatus(
  symbol: string,
  bySymbol: Map<string, PaperTradeLite>,
): { key: 'ready' | 'pending' | 'open' | 'closed'; label: string } {
  const trade = bySymbol.get(symbol)
  if (!trade) return { key: 'ready', label: 'Ready' }
  if (trade.status === 'PENDING') return { key: 'pending', label: 'Pending' }
  if (trade.status === 'OPEN') return { key: 'open', label: 'In trade' }
  if (trade.status === 'CLOSED') return { key: 'closed', label: paperStatusLabel(trade.status) }
  return { key: 'ready', label: paperStatusLabel(trade.status) }
}

export function PracticeFromScanDesk({
  scanResult,
  opportunities,
  paperTrades,
  paperEnabled,
  onEnablePaper,
  baseUrl,
  chartCandles,
  focusSymbol,
  onFocusSymbol,
  formatPrice,
  formatDateTime,
  coveragePct,
  dataAsOf,
  onRefresh,
  refreshing,
  onArmed,
  onOpenBook,
  onTick,
  ticking,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [arming, setArming] = useState(false)
  const [error, setError] = useState('')

  const bySymbol = useMemo(() => {
    const map = new Map<string, PaperTradeLite>()
    for (const trade of paperTrades) {
      const existing = map.get(trade.symbol)
      // Prefer active watches over closed history for status column.
      if (!existing || existing.status === 'CLOSED') map.set(trade.symbol, trade)
      else if (trade.status === 'OPEN' || (trade.status === 'PENDING' && existing.status !== 'OPEN')) {
        map.set(trade.symbol, trade)
      }
    }
    return map
  }, [paperTrades])

  const armable = useMemo(
    () =>
      opportunities.filter((item) => {
        const qty = Number(item.quantity ?? 0)
        if (!Number.isFinite(qty) || qty <= 0) return false
        const status = practiceStatus(item.symbol, bySymbol)
        return status.key === 'ready' || status.key === 'closed'
      }),
    [opportunities, bySymbol],
  )

  const [chartFocus, setChartFocus] = useState<string | null>(null)

  useEffect(() => {
    setSelected((prev) => {
      const next = new Set<string>()
      for (const symbol of prev) {
        if (opportunities.some((item) => item.symbol === symbol)) next.add(symbol)
      }
      return next
    })
  }, [opportunities])

  useEffect(() => {
    if (focusSymbol && opportunities.some((item) => item.symbol === focusSymbol)) {
      setChartFocus(focusSymbol)
      return
    }
    setChartFocus((prev) => {
      if (prev && opportunities.some((item) => item.symbol === prev)) return prev
      return opportunities[0]?.symbol ?? null
    })
  }, [opportunities, focusSymbol])

  const focused =
    opportunities.find((item) => item.symbol === (chartFocus || focusSymbol)) ||
    opportunities[0] ||
    null

  const chartLevels = useMemo(() => {
    if (!focused) return {}
    const isShort = focused.candidate.direction === 'SHORT'
    return {
      resistance: isShort ? null : focused.evidence.resistance,
      support: isShort ? focused.evidence.resistance : null,
      entry: focused.candidate.entry_price,
      stop: focused.candidate.stop_loss,
      target: focused.candidate.target,
      breakoutIndex: focused.evidence.breakout_candle_index,
      retestIndex: focused.evidence.retest_candle_index,
      confirmationIndex: focused.evidence.confirmation_candle_index,
    }
  }, [focused])

  const allArmableSelected =
    armable.length > 0 && armable.every((item) => selected.has(item.symbol))

  function focusRow(symbol: string) {
    setChartFocus(symbol)
    onFocusSymbol(symbol)
  }

  function toggle(symbol: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
    focusRow(symbol)
  }

  function toggleAllArmable() {
    if (allArmableSelected) {
      setSelected(new Set())
      return
    }
    setSelected(new Set(armable.map((item) => item.symbol)))
  }

  async function armSelected() {
    const items = opportunities.filter((item) => selected.has(item.symbol) && Number(item.quantity ?? 0) > 0)
    if (items.length === 0) {
      setError('Select at least one sized setup to arm.')
      return
    }
    if (!paperEnabled) onEnablePaper()
    setArming(true)
    setError('')
    try {
      const res = await fetch(`${baseUrl}/api/v1/paper/arm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: items.map((item) => ({
            symbol: item.symbol,
            direction: item.candidate.direction,
            entry_price: item.candidate.entry_price,
            stop_loss: item.candidate.stop_loss,
            target: item.candidate.target,
            quantity: item.quantity,
            risk_amount: item.risk_amount,
            setup_name: item.candidate.setup_name,
            quality_score: item.quality_score,
            scan_run_id: scanResult.scan_run_id ?? null,
          })),
        }),
      })
      if (!res.ok) {
        const detail = await res.text()
        throw new Error(detail || 'Arm failed')
      }
      const data = (await res.json()) as { message?: string; opened?: number }
      onArmed(data.message || `Armed ${data.opened ?? items.length} practice watch(es)`)
      setSelected(new Set())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Arm failed')
    } finally {
      setArming(false)
    }
  }

  const selectedCount = [...selected].filter((symbol) =>
    armable.some((item) => item.symbol === symbol),
  ).length

  return (
    <section className="practice-scan" aria-label="Practice from scan">
      <div className="practice-scan-banner" role="note">
        <strong>{PAPER_PRACTICE_CLAIM}</strong>
        <span>Waits for live price to reach entry, then manages safety exit / profit goal — no fees modeled.</span>
      </div>

      <header className="practice-scan-head">
        <div>
          <h2>Ready to trade now</h2>
          <p className="field-hint">
            Opt-in practice watches from this scan’s eligible setups. Engine levels only.
          </p>
        </div>
        <div className="practice-scan-actions">
          <button type="button" className="secondary-button find-tool-btn" onClick={onTick} disabled={ticking}>
            Update prices
          </button>
          <button type="button" className="secondary-button find-tool-btn" onClick={onOpenBook}>
            Open practice book
          </button>
        </div>
      </header>

      {!paperEnabled ? (
        <div className="practice-scan-enable">
          <p>Practice mode is off. Arming will turn it on for this session.</p>
          <button type="button" className="secondary-button find-tool-btn" onClick={onEnablePaper}>
            Enable practice
          </button>
        </div>
      ) : null}

      {error ? <div className="status error">{error}</div> : null}

      <div className="practice-scan-layout">
        <div className="practice-scan-main">
          {opportunities.length === 0 ? (
            <div className="empty-state">
              <strong>No eligible setups</strong>
              <span>Run Find setups first — only confirmed eligibles can be armed for practice.</span>
            </div>
          ) : (
            <div className="practice-scan-table-wrap">
              <table className="practice-scan-table">
                <thead>
                  <tr>
                    <th scope="col" className="check">
                      <input
                        type="checkbox"
                        checked={allArmableSelected}
                        onChange={toggleAllArmable}
                        aria-label="Select all armable setups"
                        disabled={armable.length === 0}
                      />
                    </th>
                    <th scope="col">Symbol</th>
                    <th scope="col">Direction</th>
                    <th scope="col" className="num">
                      Entry
                    </th>
                    <th scope="col" className="num">
                      Stop
                    </th>
                    <th scope="col" className="num">
                      Target
                    </th>
                    <th scope="col" className="num">
                      Qty
                    </th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {opportunities.map((item) => {
                    const status = practiceStatus(item.symbol, bySymbol)
                    const trade = bySymbol.get(item.symbol)
                    const qty = Number(item.quantity ?? 0)
                    const canArm = qty > 0 && (status.key === 'ready' || status.key === 'closed')
                    const isShort = item.candidate.direction === 'SHORT'
                    const focusedRow = focused?.symbol === item.symbol
                    return (
                      <tr
                        key={item.symbol}
                        className={`${focusedRow ? 'is-focused' : ''} ${selected.has(item.symbol) ? 'is-selected' : ''}`}
                        onClick={() => focusRow(item.symbol)}
                      >
                        <td className="check">
                          <input
                            type="checkbox"
                            checked={selected.has(item.symbol)}
                            disabled={!canArm}
                            onChange={() => toggle(item.symbol)}
                            onClick={(e) => e.stopPropagation()}
                            aria-label={`Select ${item.symbol}`}
                          />
                        </td>
                        <td className="sym">{item.symbol}</td>
                        <td>
                          <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                            {directionLabel(item.candidate.direction)}
                          </span>
                        </td>
                        <td className="num">{formatPrice(item.candidate.entry_price)}</td>
                        <td className="num">{formatPrice(item.candidate.stop_loss)}</td>
                        <td className="num">{formatPrice(item.candidate.target)}</td>
                        <td className="num">{qty > 0 ? qty : '—'}</td>
                        <td>
                          <span className={`practice-status-pill is-${status.key}`}>{status.label}</span>
                          {trade?.last_mark_price != null ? (
                            <span className="practice-status-live">
                              Live{' '}
                              <LiveValue
                                value={trade.last_mark_price}
                                formatted={formatPrice(trade.last_mark_price)}
                              />
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <aside className="practice-scan-rail">
          <button
            type="button"
            className="primary-button practice-arm-btn"
            disabled={arming || selectedCount === 0}
            onClick={() => void armSelected()}
          >
            {arming ? 'Arming…' : `Arm selected for practice${selectedCount ? ` (${selectedCount})` : ''}`}
          </button>
          <p className="field-hint practice-arm-hint">
            Creates pending watches only. No broker order is placed.
          </p>
          <div className="practice-scan-chart-card">
            <h3 className="inspect-tile-label">
              Price action{focused ? ` · ${focused.symbol}` : ''}
            </h3>
            {focused ? (
              <SetupChart candles={chartCandles} levels={chartLevels} height={280} variant="inspect" />
            ) : (
              <p className="field-hint">Select a row to preview Entry / Stop / Target.</p>
            )}
          </div>
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
