import React, { useEffect, useMemo, useRef, useState } from 'react'
import { SetupChart, type ChartCandle } from './SetupChart'
import { directionLabel, formingStageLabel } from '../terminology'

export type DetailTab = 'overview' | 'setup' | 'technical' | 'fno' | 'news'

type Opportunity = {
  symbol: string
  candidate: {
    direction: string
    entry_price: string | number
    stop_loss: string | number
    target: string | number
    risk_reward_ratio: string | number
    setup_name: string
  }
  evidence: {
    resistance: string | number
    breakout_candle_index: number
    breakout_candle_time: string
    retest_candle_index: number
    retest_candle_time: string
    confirmation_candle_index: number
    confirmation_candle_time: string
    atr_value: string | number
    volume_sma_value: string | number
    breakout_volume: number | null
    retest_low: string | number
    confirmation_volume: number | null
    decision: string
    direction?: string
    structure_label?: string | null
    retest_label?: string | null
  }
  quality_score?: string | number | null
  quantity?: number | null
  risk_amount?: string | number | null
  narrative?: string | null
  invalidation?: string | null
  current_price?: string | number | null
  current_price_change_percent?: string | number | null
}

type FormingSetup = {
  symbol: string
  stage: string
  resistance: string | number
  breakout_candle_index: number
  retest_candle_index?: number | null
  retest_low?: string | number | null
  bars_remaining: number
  reason: string
  narrative?: string | null
  current_price?: string | number | null
  current_price_change_percent?: string | number | null
  direction?: string
  structure_label?: string | null
}

type Formatters = {
  formatPrice: (value: string | number | null | undefined) => string
  formatNumber: (value: string | number | null | undefined, digits?: number) => string
  formatPercent: (value: string | number | null | undefined) => string
  formatRatio: (value: string | number | null | undefined) => string
  formatVolume: (value: string | number | null | undefined) => string
  formatDateTime: (value: string | null | undefined) => string
  formatBarRef: (index: number, time: string) => { bar: string; when: string }
  valueClass: (value: string | number) => string
}

type Props = {
  baseUrl: string
  scanStart: string
  scanEnd: string
  chartCandles: ChartCandle[]
  opportunity: Opportunity | null
  forming: FormingSetup | null
  confirmationMatchesScanEnd: (opportunity: Opportunity) => boolean
  onClose: () => void
  formatters: Formatters
}

type OverviewPayload = {
  performance: { label: string; change_percent: string | number | null }[]
  high_52w: string | number | null
  low_52w: string | number | null
  last_close: string | number | null
  last_volume: number | null
  current_price: string | number | null
  current_price_change_percent: string | number | null
  candle_count: number
}

type TechnicalPayload = {
  indicators: { name: string; value: string | number | null; signal: string; detail: string }[]
  pivots: {
    pivot: string | number
    resistance_1: string | number
    resistance_2: string | number
    resistance_3: string | number
    support_1: string | number
    support_2: string | number
    support_3: string | number
  } | null
  volume_vs_sma: string | number | null
}

type FnoPayload = {
  status: string
  detail?: string | null
  spot: string | number | null
  pcr: string | number | null
  expiry: string | null
  rows: {
    strike: string | number | null
    call_ltp: string | number | null
    call_oi: string | number | null
    call_iv: string | number | null
    put_ltp: string | number | null
    put_oi: string | number | null
    put_iv: string | number | null
  }[]
}

type NewsPayload = {
  status: string
  detail?: string | null
  announcements: { title: string; published_at: string | null; source: string; category: string; url: string | null }[]
  events: { title: string; published_at: string | null; source: string; category: string; url: string | null }[]
}

type InsightPayload = {
  title: string
  bullets: string[]
  provider: string
  grounded: boolean
}

const TABS: { id: DetailTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'setup', label: 'Setup' },
  { id: 'technical', label: 'Technical' },
  { id: 'fno', label: 'F&O' },
  { id: 'news', label: 'News & Events' },
]

function useLiveFlash(value: string | number | null | undefined) {
  const previous = useRef<number | null>(null)
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    const numeric = value == null || value === '' ? null : Number(value)
    if (numeric == null || !Number.isFinite(numeric)) {
      previous.current = null
      return
    }
    if (previous.current != null && numeric !== previous.current) {
      setFlash(numeric > previous.current ? 'up' : 'down')
      const timer = window.setTimeout(() => setFlash(null), 650)
      previous.current = numeric
      return () => window.clearTimeout(timer)
    }
    previous.current = numeric
  }, [value])

  return flash
}

function cacheKey(symbol: string, tab: DetailTab, fnoExpiry: string) {
  return tab === 'fno' ? `${symbol}:${tab}:${fnoExpiry}` : `${symbol}:${tab}`
}

export function StockDetailDrawer({
  baseUrl,
  scanStart,
  scanEnd,
  chartCandles,
  opportunity,
  forming,
  confirmationMatchesScanEnd,
  onClose,
  formatters,
}: Props) {
  const symbol = opportunity?.symbol ?? forming?.symbol ?? ''
  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [fnoExpiry, setFnoExpiry] = useState('current_month')
  const [overview, setOverview] = useState<OverviewPayload | null>(null)
  const [technical, setTechnical] = useState<TechnicalPayload | null>(null)
  const [fno, setFno] = useState<FnoPayload | null>(null)
  const [news, setNews] = useState<NewsPayload | null>(null)
  const [insights, setInsights] = useState<Partial<Record<DetailTab, InsightPayload>>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const loadedKeys = useRef<Set<string>>(new Set())
  const opportunityRef = useRef(opportunity)
  const formingRef = useRef(forming)
  const tabDataRef = useRef({ overview, technical, fno, news })
  opportunityRef.current = opportunity
  formingRef.current = forming
  tabDataRef.current = { overview, technical, fno, news }
  const insight = insights[activeTab] ?? null

  const {
    formatPrice,
    formatNumber,
    formatPercent,
    formatRatio,
    formatVolume,
    formatDateTime,
    formatBarRef,
    valueClass,
  } = formatters

  const headerPrice = opportunity?.current_price ?? forming?.current_price ?? overview?.current_price
  const headerChange =
    opportunity?.current_price_change_percent ??
    forming?.current_price_change_percent ??
    overview?.current_price_change_percent
  const priceFlash = useLiveFlash(headerPrice)
  const isShort =
    opportunity?.candidate.direction === 'SHORT' || forming?.direction === 'SHORT'
  const structureLabel = isShort ? 'Floor (support)' : 'Ceiling (resistance)'
  const retestLabel = isShort ? 'Retest high' : 'Retest low'
  const chartLevels = {
    resistance: isShort
      ? opportunity?.evidence.retest_low ?? forming?.retest_low
      : opportunity?.evidence.resistance ?? forming?.resistance,
    support: isShort
      ? opportunity?.evidence.resistance ?? forming?.resistance
      : opportunity?.evidence.retest_low ?? forming?.retest_low,
    entry: opportunity?.candidate.entry_price,
    stop: opportunity?.candidate.stop_loss,
    target: opportunity?.candidate.target,
    breakoutIndex: opportunity?.evidence.breakout_candle_index ?? forming?.breakout_candle_index,
    retestIndex: opportunity?.evidence.retest_candle_index ?? forming?.retest_candle_index,
    confirmationIndex: opportunity?.evidence.confirmation_candle_index,
  }

  const rangeQuery = useMemo(() => {
    const startDate = new Date(scanStart)
    const endDate = new Date(scanEnd)
    return new URLSearchParams({
      timeframe: '1d',
      start: startDate.toISOString(),
      end: endDate.toISOString(),
    })
  }, [scanStart, scanEnd])

  useEffect(() => {
    setActiveTab('overview')
    setOverview(null)
    setTechnical(null)
    setFno(null)
    setNews(null)
    setInsights({})
    setError('')
    loadedKeys.current = new Set()
  }, [symbol])

  useEffect(() => {
    if (!symbol || activeTab === 'setup') {
      setLoading(false)
      return
    }

    const key = cacheKey(symbol, activeTab, fnoExpiry)
    if (loadedKeys.current.has(key)) {
      setLoading(false)
      return
    }

    let cancelled = false
    const data = tabDataRef.current
    const hasExisting =
      (activeTab === 'overview' && data.overview) ||
      (activeTab === 'technical' && data.technical) ||
      (activeTab === 'fno' && data.fno) ||
      (activeTab === 'news' && data.news)

    const setTabInsight = (payload: InsightPayload) => {
      setInsights((current) => ({ ...current, [activeTab]: payload }))
    }

    const load = async () => {
      if (!hasExisting) setLoading(true)
      setError('')
      try {
        if (activeTab === 'overview') {
          const response = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/overview?${rangeQuery}`,
          )
          if (!response.ok) throw new Error('Failed to load overview')
          const payload = (await response.json()) as OverviewPayload
          if (cancelled) return
          setOverview(payload)
          const currentOpportunity = opportunityRef.current
          const currentForming = formingRef.current
          const insightResp = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/insight`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                tab: 'overview',
                context: {
                  symbol,
                  performance: payload.performance,
                  high_52w: payload.high_52w,
                  low_52w: payload.low_52w,
                  last_close: payload.last_close,
                  setup: currentOpportunity
                    ? {
                        narrative: currentOpportunity.narrative,
                        entry: currentOpportunity.candidate.entry_price,
                        stop: currentOpportunity.candidate.stop_loss,
                        target: currentOpportunity.candidate.target,
                      }
                    : currentForming
                      ? { narrative: currentForming.narrative, stage: currentForming.stage }
                      : null,
                },
              }),
            },
          )
          if (insightResp.ok && !cancelled) setTabInsight((await insightResp.json()) as InsightPayload)
        }

        if (activeTab === 'technical') {
          const response = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/technical?${rangeQuery}`,
          )
          if (!response.ok) throw new Error('Failed to load technicals')
          const payload = (await response.json()) as TechnicalPayload
          if (cancelled) return
          setTechnical(payload)
          const insightResp = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/insight`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ tab: 'technical', context: { symbol, ...payload } }),
            },
          )
          if (insightResp.ok && !cancelled) setTabInsight((await insightResp.json()) as InsightPayload)
        }

        if (activeTab === 'fno') {
          const response = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/fno?expiry=${encodeURIComponent(fnoExpiry)}`,
          )
          if (!response.ok) throw new Error('Failed to load F&O')
          if (!cancelled) setFno((await response.json()) as FnoPayload)
        }

        if (activeTab === 'news') {
          const response = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/news-events`,
          )
          if (!response.ok) throw new Error('Failed to load news')
          const payload = (await response.json()) as NewsPayload
          if (cancelled) return
          setNews(payload)
          const insightResp = await fetch(
            `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/insight`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                tab: 'news',
                context: {
                  symbol,
                  announcements: payload.announcements,
                  events: payload.events,
                },
              }),
            },
          )
          if (insightResp.ok && !cancelled) setTabInsight((await insightResp.json()) as InsightPayload)
        }

        if (!cancelled) loadedKeys.current.add(key)
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Failed to load tab')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
    // Intentionally exclude opportunity/forming — live quote ticks must not refetch tabs.
  }, [activeTab, baseUrl, fnoExpiry, rangeQuery, symbol])

  const atmRows = useMemo(() => {
    if (!fno?.rows?.length) return []
    const spot = Number(fno.spot)
    if (!Number.isFinite(spot)) return fno.rows.slice(0, 21)
    const ranked = [...fno.rows].sort(
      (a, b) => Math.abs(Number(a.strike) - spot) - Math.abs(Number(b.strike) - spot),
    )
    const near = new Set(ranked.slice(0, 21).map((row) => String(row.strike)))
    return fno.rows.filter((row) => near.has(String(row.strike)))
  }, [fno])

  const maxCallOi = Math.max(...(fno?.rows.map((row) => Number(row.call_oi) || 0) ?? [0]))
  const maxPutOi = Math.max(...(fno?.rows.map((row) => Number(row.put_oi) || 0) ?? [0]))

  return (
    <div className="detail-overlay" role="presentation" onClick={onClose}>
      <div
        className="detail-drawer detail-drawer-tabs"
        role="dialog"
        aria-modal="true"
        aria-labelledby="opportunity-detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="detail-drawer-header">
          <div className="opportunity-detail-header">
            <h3 id="opportunity-detail-title">{symbol}</h3>
            <div className={`detail-ltp-block live-tick ${priceFlash ? `flash-${priceFlash}` : ''}`}>
              <strong>{formatPrice(headerPrice)}</strong>
              <span className={valueClass(headerChange ?? 0)}>{formatPercent(headerChange)}</span>
              <em className="live-dot" aria-hidden="true" />
            </div>
            {opportunity ? (
              <span
                className={`now-badge ${
                  confirmationMatchesScanEnd(opportunity) ? 'now-active' : 'now-neutral'
                }`}
              >
                {confirmationMatchesScanEnd(opportunity)
                  ? 'Ready now — last price bar confirmed the idea'
                  : 'Needs confirmation on the latest price bar'}
              </span>
            ) : (
              <span className="now-badge now-neutral">Almost ready — no full trade plan yet</span>
            )}
          </div>
          <button type="button" className="detail-close" aria-label="Close opportunity detail" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="detail-tab-bar" role="tablist" aria-label="Stock research tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`detail-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="detail-tab-panel panel-fade" key={`${symbol}-${activeTab}-${fnoExpiry}`}>
          {loading && (
            <div className="soft-loader" aria-live="polite">
              <span className="soft-loader-bar" />
              <span className="field-hint">Refreshing {activeTab}…</span>
            </div>
          )}
          {error && <div className="status error">{error}</div>}

          {activeTab === 'overview' && overview && (
            <>
              <div className="section-box elevate-card">
                <h3>Performance</h3>
                <div className="perf-grid">
                  {overview.performance.map((item, index) => (
                    <div
                      key={item.label}
                      className="perf-card stagger-item"
                      style={{ animationDelay: `${index * 40}ms` }}
                    >
                      <span>{item.label}</span>
                      <strong className={valueClass(item.change_percent ?? 0)}>
                        {formatPercent(item.change_percent)}
                      </strong>
                    </div>
                  ))}
                </div>
                <dl>
                  <div>
                    <dt>52W high</dt>
                    <dd>{formatPrice(overview.high_52w)}</dd>
                  </div>
                  <div>
                    <dt>52W low</dt>
                    <dd>{formatPrice(overview.low_52w)}</dd>
                  </div>
                  <div>
                    <dt>Last close</dt>
                    <dd>{formatPrice(overview.last_close)}</dd>
                  </div>
                  <div>
                    <dt>Volume</dt>
                    <dd>{formatVolume(overview.last_volume)}</dd>
                  </div>
                </dl>
              </div>
              <div className="section-box elevate-card">
                <h3>Chart</h3>
                <SetupChart candles={chartCandles} levels={chartLevels} />
              </div>
              {insight && (
                <div className="section-box insight-card elevate-card">
                  <h3>{insight.title}</h3>
                  <p className="field-hint">
                    {insight.provider === 'gemini' ? 'Gemini Flash (grounded)' : 'Template summary'} · facts only
                  </p>
                  <ul>
                    {insight.bullets.map((bullet) => (
                      <li key={bullet}>{bullet}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {activeTab === 'setup' && (
            <>
              <p className="field-hint">
                {opportunity?.narrative ??
                  forming?.narrative ??
                  (isShort
                    ? 'A sell-short idea needs three steps: price breaks down, comes back to retest, then confirms on the last candle.'
                    : 'A buy idea needs three steps: price breaks out, comes back to retest, then confirms on the last candle.')}
              </p>
              <div className="section-box elevate-card">
                <h3>Chart</h3>
                <SetupChart candles={chartCandles} levels={chartLevels} />
              </div>

              {opportunity && (
                <div className="section-box elevate-card">
                  <h3>Trade plan</h3>
                  <dl>
                    <div>
                      <dt>Trade type</dt>
                      <dd>
                        <span
                          className={`direction-pill ${
                            opportunity.candidate.direction === 'LONG' ? 'long' : 'short'
                          }`}
                        >
                          {directionLabel(opportunity.candidate.direction)}
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>Buy/sell at</dt>
                      <dd>{formatPrice(opportunity.candidate.entry_price)}</dd>
                    </div>
                    <div>
                      <dt>Live price</dt>
                      <dd className={`live-tick ${priceFlash ? `flash-${priceFlash}` : ''}`}>
                        {formatPrice(opportunity.current_price)}
                      </dd>
                    </div>
                    <div>
                      <dt>Today</dt>
                      <dd className={valueClass(opportunity.current_price_change_percent ?? 0)}>
                        {formatPercent(opportunity.current_price_change_percent)}
                      </dd>
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
                      <dt>Setup</dt>
                      <dd className="plain-value">{opportunity.candidate.setup_name}</dd>
                    </div>
                    <div>
                      <dt>Quality</dt>
                      <dd>{formatNumber(opportunity.quality_score, 1)}</dd>
                    </div>
                    <div>
                      <dt>Shares</dt>
                      <dd>{opportunity.quantity ?? '—'}</dd>
                    </div>
                    <div>
                      <dt>₹ you could lose</dt>
                      <dd>{formatPrice(opportunity.risk_amount)}</dd>
                    </div>
                  </dl>
                  {opportunity.invalidation && (
                    <p className="invalidation-copy">{opportunity.invalidation}</p>
                  )}
                </div>
              )}

              {opportunity && (
                <div className="section-box elevate-card">
                  <h3>Evidence</h3>
                  <dl>
                    <div>
                      <dt>Decision</dt>
                      <dd className="evidence-decision">{opportunity.evidence.decision}</dd>
                    </div>
                    <div>
                      <dt>{structureLabel}</dt>
                      <dd>{formatPrice(opportunity.evidence.resistance)}</dd>
                    </div>
                    <div>
                      <dt>Breakout</dt>
                      <dd className="bar-ref">
                        <span>
                          {
                            formatBarRef(
                              opportunity.evidence.breakout_candle_index,
                              opportunity.evidence.breakout_candle_time,
                            ).bar
                          }
                        </span>
                        <small>
                          {
                            formatBarRef(
                              opportunity.evidence.breakout_candle_index,
                              opportunity.evidence.breakout_candle_time,
                            ).when
                          }
                        </small>
                      </dd>
                    </div>
                    <div>
                      <dt>Retest</dt>
                      <dd className="bar-ref">
                        <span>
                          {
                            formatBarRef(
                              opportunity.evidence.retest_candle_index,
                              opportunity.evidence.retest_candle_time,
                            ).bar
                          }
                        </span>
                        <small>
                          {
                            formatBarRef(
                              opportunity.evidence.retest_candle_index,
                              opportunity.evidence.retest_candle_time,
                            ).when
                          }
                        </small>
                      </dd>
                    </div>
                    <div>
                      <dt>Confirmation</dt>
                      <dd className="bar-ref">
                        <span>
                          {
                            formatBarRef(
                              opportunity.evidence.confirmation_candle_index,
                              opportunity.evidence.confirmation_candle_time,
                            ).bar
                          }
                        </span>
                        <small>
                          {
                            formatBarRef(
                              opportunity.evidence.confirmation_candle_index,
                              opportunity.evidence.confirmation_candle_time,
                            ).when
                          }
                        </small>
                      </dd>
                    </div>
                    <div>
                      <dt>ATR</dt>
                      <dd>{formatNumber(opportunity.evidence.atr_value, 2)}</dd>
                    </div>
                    <div>
                      <dt>Volume SMA</dt>
                      <dd>{formatVolume(opportunity.evidence.volume_sma_value)}</dd>
                    </div>
                    <div>
                      <dt>{isShort ? 'Breakdown volume' : 'Breakout volume'}</dt>
                      <dd>{formatVolume(opportunity.evidence.breakout_volume)}</dd>
                    </div>
                    <div>
                      <dt>{retestLabel}</dt>
                      <dd>{formatPrice(opportunity.evidence.retest_low)}</dd>
                    </div>
                    <div>
                      <dt>Confirmation volume</dt>
                      <dd>{formatVolume(opportunity.evidence.confirmation_volume)}</dd>
                    </div>
                  </dl>
                </div>
              )}

              {forming && (
                <div className="section-box elevate-card">
                  <h3>Almost ready</h3>
                  <dl>
                    <div>
                      <dt>Stage</dt>
                      <dd>{formingStageLabel(forming.stage)}</dd>
                    </div>
                    <div>
                      <dt>{structureLabel}</dt>
                      <dd>{formatPrice(forming.resistance)}</dd>
                    </div>
                    <div>
                      <dt>Current price</dt>
                      <dd className={`live-tick ${priceFlash ? `flash-${priceFlash}` : ''}`}>
                        {formatPrice(forming.current_price)}
                      </dd>
                    </div>
                    <div>
                      <dt>Change</dt>
                      <dd className={valueClass(forming.current_price_change_percent ?? 0)}>
                        {formatPercent(forming.current_price_change_percent)}
                      </dd>
                    </div>
                    <div>
                      <dt>Bars remaining</dt>
                      <dd>{forming.bars_remaining}</dd>
                    </div>
                    <div>
                      <dt>Why</dt>
                      <dd className="evidence-decision">{forming.reason}</dd>
                    </div>
                  </dl>
                </div>
              )}
            </>
          )}

          {activeTab === 'technical' && technical && (
            <>
              <div className="section-box elevate-card">
                <h3>Key technicals</h3>
                <div className="tech-grid">
                  {technical.indicators.map((item, index) => (
                    <div
                      key={item.name}
                      className={`tech-card signal-${item.signal} stagger-item`}
                      style={{ animationDelay: `${index * 35}ms` }}
                    >
                      <span>{item.name}</span>
                      <strong>{item.value == null ? '—' : formatNumber(item.value, 2)}</strong>
                      <em>{item.signal}</em>
                      <small>{item.detail}</small>
                    </div>
                  ))}
                </div>
              </div>
              {technical.pivots && (
                <div className="section-box elevate-card">
                  <h3>Pivot points</h3>
                  <dl>
                    <div>
                      <dt>Pivot</dt>
                      <dd>{formatPrice(technical.pivots.pivot)}</dd>
                    </div>
                    <div>
                      <dt>R1 / R2 / R3</dt>
                      <dd>
                        {formatPrice(technical.pivots.resistance_1)} /{' '}
                        {formatPrice(technical.pivots.resistance_2)} /{' '}
                        {formatPrice(technical.pivots.resistance_3)}
                      </dd>
                    </div>
                    <div>
                      <dt>S1 / S2 / S3</dt>
                      <dd>
                        {formatPrice(technical.pivots.support_1)} /{' '}
                        {formatPrice(technical.pivots.support_2)} /{' '}
                        {formatPrice(technical.pivots.support_3)}
                      </dd>
                    </div>
                  </dl>
                </div>
              )}
              {insight && (
                <div className="section-box insight-card elevate-card">
                  <h3>{insight.title}</h3>
                  <p className="field-hint">
                    {insight.provider === 'gemini' ? 'Gemini Flash (grounded)' : 'Template summary'} · no invented levels
                  </p>
                  <ul>
                    {insight.bullets.map((bullet) => (
                      <li key={bullet}>{bullet}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {activeTab === 'fno' && (
            <>
              <div className="field-group fno-expiry">
                <label htmlFor="fno-expiry">Expiry</label>
                <select
                  id="fno-expiry"
                  value={fnoExpiry}
                  onChange={(event) => {
                    loadedKeys.current.delete(cacheKey(symbol, 'fno', event.target.value))
                    setFnoExpiry(event.target.value)
                  }}
                >
                  <option value="current_week">Current week</option>
                  <option value="next_week">Next week</option>
                  <option value="current_month">Current month</option>
                  <option value="next_month">Next month</option>
                </select>
              </div>
              {fno && fno.status !== 'ok' && (
                <div className="empty-state">
                  <strong>F&O unavailable</strong>
                  <span>{fno.detail || 'Option chain could not be loaded for this symbol.'}</span>
                </div>
              )}
              {fno && fno.status === 'ok' && (
                <div className="section-box elevate-card">
                  <h3>Option chain {fno.expiry ? `· ${fno.expiry}` : ''}</h3>
                  <div className="result-grid">
                    <div>
                      <strong>Spot:</strong> {formatPrice(fno.spot)}
                    </div>
                    <div>
                      <strong>PCR:</strong> {formatNumber(fno.pcr, 2)}
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Call live price</th>
                          <th>Call OI</th>
                          <th>Call IV</th>
                          <th>Strike</th>
                          <th>Put IV</th>
                          <th>Put OI</th>
                          <th>Put live price</th>
                        </tr>
                      </thead>
                      <tbody>
                        {atmRows.map((row) => (
                          <tr
                            key={String(row.strike)}
                            className={
                              Number(row.call_oi) === maxCallOi || Number(row.put_oi) === maxPutOi
                                ? 'row-selected'
                                : undefined
                            }
                          >
                            <td className="num-cell">{formatPrice(row.call_ltp)}</td>
                            <td className="num-cell">{formatNumber(row.call_oi, 0)}</td>
                            <td className="num-cell">{formatNumber(row.call_iv, 1)}</td>
                            <td className="num-cell symbol-cell">{formatNumber(row.strike, 0)}</td>
                            <td className="num-cell">{formatNumber(row.put_iv, 1)}</td>
                            <td className="num-cell">{formatNumber(row.put_oi, 0)}</td>
                            <td className="num-cell">{formatPrice(row.put_ltp)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {activeTab === 'news' && news && (
            <>
              {news.status !== 'ok' && (
                <div className="empty-state">
                  <strong>News feed unavailable</strong>
                  <span>{news.detail || 'NSE announcements could not be loaded right now.'}</span>
                </div>
              )}
              <div className="section-box elevate-card">
                <h3>Announcements</h3>
                {news.announcements.length === 0 ? (
                  <p className="field-hint">No recent announcements.</p>
                ) : (
                  <ul className="news-list">
                    {news.announcements.map((item) => (
                      <li key={`${item.title}-${item.published_at}`}>
                        <strong>{item.title}</strong>
                        <span>
                          {item.source} · {item.published_at ? formatDateTime(item.published_at) : '—'}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="section-box elevate-card">
                <h3>Events</h3>
                {news.events.length === 0 ? (
                  <p className="field-hint">No upcoming corporate actions found.</p>
                ) : (
                  <ul className="news-list">
                    {news.events.map((item) => (
                      <li key={`${item.title}-${item.published_at}`}>
                        <strong>{item.title}</strong>
                        <span>
                          {item.category} · {item.published_at || '—'}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {insight && (
                <div className="section-box insight-card elevate-card">
                  <h3>{insight.title}</h3>
                  <p className="field-hint">
                    {insight.provider === 'gemini' ? 'Gemini Flash (grounded)' : 'Template summary'} · headlines only
                  </p>
                  <ul>
                    {insight.bullets.map((bullet) => (
                      <li key={bullet}>{bullet}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
