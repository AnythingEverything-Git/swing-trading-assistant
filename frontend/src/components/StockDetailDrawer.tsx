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
  symbol: string
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
  announcements: {
    title: string
    published_at: string | null
    source: string
    category: string
    url: string | null
  }[]
  events: {
    title: string
    published_at: string | null
    source: string
    category: string
    url: string | null
  }[]
}

type SymbolDrawerCache = {
  loadedKeys: Set<string>
  overview: OverviewPayload | null
  technical: TechnicalPayload | null
  fnoByExpiry: Record<string, FnoPayload>
  news: NewsPayload | null
}

const TECH_VISIBLE_KEY = 'tradepilot.technical.visible'

const DEFAULT_VISIBLE_INDICATORS = [
  'RSI(14)',
  'MACD(12,26,9)',
  'ATR(14)',
  'SMA 20',
  'SMA 50',
  'SMA 200',
  'Volume vs SMA20',
]

const drawerCacheBySymbol = new Map<string, SymbolDrawerCache>()

function getDrawerCache(symbol: string): SymbolDrawerCache {
  let cached = drawerCacheBySymbol.get(symbol)
  if (!cached) {
    cached = {
      loadedKeys: new Set(),
      overview: null,
      technical: null,
      fnoByExpiry: {},
      news: null,
    }
    drawerCacheBySymbol.set(symbol, cached)
  }
  return cached
}

function readVisibleIndicators(): string[] {
  try {
    const raw = window.localStorage.getItem(TECH_VISIBLE_KEY)
    if (!raw) return [...DEFAULT_VISIBLE_INDICATORS]
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === 'string')) {
      return [...DEFAULT_VISIBLE_INDICATORS]
    }
    return parsed.length > 0 ? parsed : [...DEFAULT_VISIBLE_INDICATORS]
  } catch {
    return [...DEFAULT_VISIBLE_INDICATORS]
  }
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
  symbol,
  scanStart,
  scanEnd,
  chartCandles,
  opportunity,
  forming,
  confirmationMatchesScanEnd,
  onClose,
  formatters,
}: Props) {
  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [fnoExpiry, setFnoExpiry] = useState('current_month')
  const [overview, setOverview] = useState<OverviewPayload | null>(null)
  const [technical, setTechnical] = useState<TechnicalPayload | null>(null)
  const [fno, setFno] = useState<FnoPayload | null>(null)
  const [news, setNews] = useState<NewsPayload | null>(null)
  const [fetchedOpportunity, setFetchedOpportunity] = useState<Opportunity | null>(null)
  const [setupStatus, setSetupStatus] = useState('')
  const [setupLoading, setSetupLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [visibleIndicators, setVisibleIndicators] = useState<string[]>(() => readVisibleIndicators())
  const [customizeOpen, setCustomizeOpen] = useState(false)
  const [draftIndicators, setDraftIndicators] = useState<string[]>(() => readVisibleIndicators())
  const loadedKeys = useRef<Set<string>>(new Set())
  const tabDataRef = useRef({ overview, technical, fno, news })
  tabDataRef.current = { overview, technical, fno, news }

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

  const resolvedOpportunity = opportunity ?? fetchedOpportunity
  const headerPrice =
    resolvedOpportunity?.current_price ?? forming?.current_price ?? overview?.current_price
  const headerChange =
    resolvedOpportunity?.current_price_change_percent ??
    forming?.current_price_change_percent ??
    overview?.current_price_change_percent
  const priceFlash = useLiveFlash(headerPrice)
  const isShort =
    resolvedOpportunity?.candidate.direction === 'SHORT' || forming?.direction === 'SHORT'
  const structureLabel = isShort ? 'Floor (support)' : 'Ceiling (resistance)'
  const retestLabel = isShort ? 'Retest high' : 'Retest low'
  const chartLevels = {
    resistance: isShort
      ? resolvedOpportunity?.evidence.retest_low ?? forming?.retest_low
      : resolvedOpportunity?.evidence.resistance ?? forming?.resistance,
    support: isShort
      ? resolvedOpportunity?.evidence.resistance ?? forming?.resistance
      : resolvedOpportunity?.evidence.retest_low ?? forming?.retest_low,
    entry: resolvedOpportunity?.candidate.entry_price,
    stop: resolvedOpportunity?.candidate.stop_loss,
    target: resolvedOpportunity?.candidate.target,
    breakoutIndex:
      resolvedOpportunity?.evidence.breakout_candle_index ?? forming?.breakout_candle_index,
    retestIndex: resolvedOpportunity?.evidence.retest_candle_index ?? forming?.retest_candle_index,
    confirmationIndex: resolvedOpportunity?.evidence.confirmation_candle_index,
  }

  const statusLabel = resolvedOpportunity
    ? confirmationMatchesScanEnd(resolvedOpportunity)
      ? 'Ready now'
      : 'Needs latest bar'
    : forming
      ? 'Almost ready'
      : setupLoading
        ? 'Loading setup…'
        : 'Research'

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
    if (!symbol) return
    const cached = getDrawerCache(symbol)
    setActiveTab('overview')
    setOverview(cached.overview)
    setTechnical(cached.technical)
    setFno(cached.fnoByExpiry[fnoExpiry] ?? null)
    setNews(cached.news)
    setFetchedOpportunity(null)
    setSetupStatus('')
    setError('')
    setCustomizeOpen(false)
    loadedKeys.current = cached.loadedKeys
  }, [symbol])

  useEffect(() => {
    if (!symbol || opportunity || forming) {
      if (opportunity || forming) {
        setFetchedOpportunity(null)
        setSetupStatus('')
        setSetupLoading(false)
      }
      return
    }

    let cancelled = false
    const loadSetup = async () => {
      setSetupLoading(true)
      setSetupStatus('')
      try {
        const startDate = new Date(scanStart)
        const endDate = new Date(scanEnd)
        const response = await fetch(`${baseUrl}/api/v1/strategy/evaluate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol,
            timeframe: '1d',
            start: startDate.toISOString(),
            end: endDate.toISOString(),
          }),
        })
        if (!response.ok) throw new Error('Failed to load trade setup')
        const payload = (await response.json()) as {
          has_setup: boolean
          status: string
          reason?: string | null
          candidate: Opportunity['candidate'] | null
          evidence: Opportunity['evidence'] | null
        }
        if (cancelled) return

        let currentPrice: string | number | null = null
        let changePct: string | number | null = null
        try {
          const quoteResp = await fetch(
            `${baseUrl}/api/v1/market-data/quotes?symbols=${encodeURIComponent(symbol)}`,
          )
          if (quoteResp.ok) {
            const quotes = (await quoteResp.json()) as {
              symbol: string
              current_price: string | number | null
              current_price_change_percent: string | number | null
            }[]
            const quote = quotes.find((item) => item.symbol === symbol)
            currentPrice = quote?.current_price ?? null
            changePct = quote?.current_price_change_percent ?? null
          }
        } catch {
          /* quote is best-effort */
        }

        if (payload.has_setup && payload.candidate && payload.evidence) {
          setFetchedOpportunity({
            symbol,
            candidate: payload.candidate,
            evidence: payload.evidence,
            narrative: payload.reason ?? null,
            current_price: currentPrice,
            current_price_change_percent: changePct,
          })
          setSetupStatus('')
        } else {
          setFetchedOpportunity(null)
          setSetupStatus(
            payload.reason ||
              (payload.status ? `No confirmed setup (${payload.status}).` : 'No confirmed setup for this date range.'),
          )
        }
      } catch (caught) {
        if (!cancelled) {
          setFetchedOpportunity(null)
          setSetupStatus(caught instanceof Error ? caught.message : 'Failed to load trade setup')
        }
      } finally {
        if (!cancelled) setSetupLoading(false)
      }
    }

    void loadSetup()
    return () => {
      cancelled = true
    }
  }, [baseUrl, forming, opportunity, scanEnd, scanStart, symbol])

  useEffect(() => {
    if (!symbol) {
      setLoading(false)
      return
    }
    if (activeTab === 'setup') {
      setLoading(false)
      return
    }

    const drawerCache = getDrawerCache(symbol)
    const key = cacheKey(symbol, activeTab, fnoExpiry)
    if (loadedKeys.current.has(key)) {
      if (activeTab === 'fno' && drawerCache.fnoByExpiry[fnoExpiry]) {
        setFno(drawerCache.fnoByExpiry[fnoExpiry])
      }
      setLoading(false)
      return
    }

    let cancelled = false
    const data = tabDataRef.current
    const hasExisting =
      (activeTab === 'overview' && (data.overview || drawerCache.overview)) ||
      (activeTab === 'technical' && (data.technical || drawerCache.technical)) ||
      (activeTab === 'fno' && (data.fno || drawerCache.fnoByExpiry[fnoExpiry])) ||
      (activeTab === 'news' && (data.news || drawerCache.news))

    const load = async () => {
      if (!hasExisting) setLoading(true)
      setError('')
      try {
        if (activeTab === 'overview') {
          let payload = drawerCache.overview
          if (!payload) {
            const response = await fetch(
              `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/overview?${rangeQuery}`,
            )
            if (!response.ok) throw new Error('Failed to load overview')
            payload = (await response.json()) as OverviewPayload
            if (cancelled) return
            drawerCache.overview = payload
          }
          setOverview(payload)
        }

        if (activeTab === 'technical') {
          let payload = drawerCache.technical
          if (!payload) {
            const response = await fetch(
              `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/technical?${rangeQuery}`,
            )
            if (!response.ok) throw new Error('Failed to load technicals')
            payload = (await response.json()) as TechnicalPayload
            if (cancelled) return
            drawerCache.technical = payload
          }
          setTechnical(payload)
        }

        if (activeTab === 'fno') {
          let payload = drawerCache.fnoByExpiry[fnoExpiry]
          if (!payload) {
            const response = await fetch(
              `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/fno?expiry=${encodeURIComponent(fnoExpiry)}`,
            )
            if (!response.ok) throw new Error('Failed to load F&O')
            payload = (await response.json()) as FnoPayload
            if (cancelled) return
            drawerCache.fnoByExpiry[fnoExpiry] = payload
          }
          setFno(payload)
        }

        if (activeTab === 'news') {
          let payload = drawerCache.news
          if (!payload) {
            const response = await fetch(
              `${baseUrl}/api/v1/research/${encodeURIComponent(symbol)}/news-events`,
            )
            if (!response.ok) throw new Error('Failed to load news')
            payload = (await response.json()) as NewsPayload
            if (cancelled) return
            drawerCache.news = payload
          }
          setNews(payload)
        }

        if (!cancelled) {
          loadedKeys.current.add(key)
          drawerCache.loadedKeys.add(key)
        }
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

  const atmStrike = useMemo(() => {
    if (!fno?.rows?.length) return null
    const spot = Number(fno.spot)
    if (!Number.isFinite(spot)) return null
    let best: { strike: string | number | null; distance: number } | null = null
    for (const row of fno.rows) {
      const distance = Math.abs(Number(row.strike) - spot)
      if (!Number.isFinite(distance)) continue
      if (!best || distance < best.distance) best = { strike: row.strike, distance }
    }
    return best?.strike ?? null
  }, [fno])

  const filteredIndicators = useMemo(() => {
    if (!technical) return []
    const visible = new Set(visibleIndicators)
    return technical.indicators.filter((item) => visible.has(item.name))
  }, [technical, visibleIndicators])

  const allIndicatorNames = useMemo(
    () => technical?.indicators.map((item) => item.name) ?? [],
    [technical],
  )

  return (
    <div className="detail-overlay" role="presentation">
      <div
        className="detail-drawer detail-drawer-clean"
        role="dialog"
        aria-modal="true"
        aria-labelledby="opportunity-detail-title"
      >
        <header className="detail-head">
          <div className="detail-head-main">
            <div className="detail-head-title-row">
              <h2 id="opportunity-detail-title">{symbol}</h2>
              <span className="detail-status-chip">{statusLabel}</span>
            </div>
            <div className={`detail-price-row live-tick ${priceFlash ? `flash-${priceFlash}` : ''}`}>
              <span className="detail-price">{formatPrice(headerPrice)}</span>
              <span className={`detail-change ${valueClass(headerChange ?? 0)}`}>
                {formatPercent(headerChange)}
              </span>
            </div>
          </div>
          <button type="button" className="detail-close" aria-label="Close stock detail" onClick={onClose}>
            Close
          </button>
        </header>

        <nav className="detail-tabs" role="tablist" aria-label="Stock detail tabs">
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
        </nav>

        <div className="detail-body" key={`${symbol}-${activeTab}-${fnoExpiry}`}>
          {loading && <p className="detail-loading">Loading {activeTab}…</p>}
          {error && <div className="status error">{error}</div>}

          {activeTab === 'overview' && overview && (
            <div className="detail-stack">
              <section className="detail-block">
                <h3>Performance</h3>
                <div className="metric-row">
                  {overview.performance.map((item) => (
                    <div key={item.label} className="metric-tile">
                      <span>{item.label}</span>
                      <strong className={valueClass(item.change_percent ?? 0)}>
                        {formatPercent(item.change_percent)}
                      </strong>
                    </div>
                  ))}
                </div>
                <div className="metric-row metric-row-stats">
                  <div className="metric-tile">
                    <span>52W high</span>
                    <strong>{formatPrice(overview.high_52w)}</strong>
                  </div>
                  <div className="metric-tile">
                    <span>52W low</span>
                    <strong>{formatPrice(overview.low_52w)}</strong>
                  </div>
                  <div className="metric-tile">
                    <span>Last close</span>
                    <strong>{formatPrice(overview.last_close)}</strong>
                  </div>
                  <div className="metric-tile">
                    <span>Volume</span>
                    <strong>{formatVolume(overview.last_volume)}</strong>
                  </div>
                </div>
              </section>
              <section className="detail-block">
                <h3>Chart</h3>
                <SetupChart candles={chartCandles} levels={chartLevels} />
              </section>
            </div>
          )}

          {activeTab === 'setup' && (
            <div className="detail-stack">
              {(resolvedOpportunity?.narrative || forming?.narrative) && (
                <p className="detail-lede">{resolvedOpportunity?.narrative ?? forming?.narrative}</p>
              )}
              <section className="detail-block">
                <h3>Chart</h3>
                <SetupChart candles={chartCandles} levels={chartLevels} />
              </section>

              {resolvedOpportunity && (
                <section className="detail-block">
                  <h3>Trade plan</h3>
                  <div className="kv-grid">
                    <div>
                      <span>Trade type</span>
                      <strong>
                        <span
                          className={`direction-pill ${
                            resolvedOpportunity.candidate.direction === 'LONG' ? 'long' : 'short'
                          }`}
                        >
                          {directionLabel(resolvedOpportunity.candidate.direction)}
                        </span>
                      </strong>
                    </div>
                    <div>
                      <span>Buy/sell at</span>
                      <strong>{formatPrice(resolvedOpportunity.candidate.entry_price)}</strong>
                    </div>
                    <div>
                      <span>Live price</span>
                      <strong className={`live-tick ${priceFlash ? `flash-${priceFlash}` : ''}`}>
                        {formatPrice(resolvedOpportunity.current_price)}
                      </strong>
                    </div>
                    <div>
                      <span>Today</span>
                      <strong className={valueClass(resolvedOpportunity.current_price_change_percent ?? 0)}>
                        {formatPercent(resolvedOpportunity.current_price_change_percent)}
                      </strong>
                    </div>
                    <div>
                      <span>Safety exit</span>
                      <strong>{formatPrice(resolvedOpportunity.candidate.stop_loss)}</strong>
                    </div>
                    <div>
                      <span>Profit goal</span>
                      <strong>{formatPrice(resolvedOpportunity.candidate.target)}</strong>
                    </div>
                    <div>
                      <span>Reward vs risk</span>
                      <strong>{formatRatio(resolvedOpportunity.candidate.risk_reward_ratio)}</strong>
                    </div>
                    <div>
                      <span>Setup</span>
                      <strong>{resolvedOpportunity.candidate.setup_name}</strong>
                    </div>
                    <div>
                      <span>Quality</span>
                      <strong>{formatNumber(resolvedOpportunity.quality_score, 1)}</strong>
                    </div>
                    <div>
                      <span>Shares</span>
                      <strong>{resolvedOpportunity.quantity ?? '—'}</strong>
                    </div>
                    <div>
                      <span>₹ you could lose</span>
                      <strong>{formatPrice(resolvedOpportunity.risk_amount)}</strong>
                    </div>
                  </div>
                  {resolvedOpportunity.invalidation && (
                    <p className="invalidation-copy">{resolvedOpportunity.invalidation}</p>
                  )}
                </section>
              )}

              {resolvedOpportunity && (
                <section className="detail-block">
                  <h3>Evidence</h3>
                  <div className="kv-grid">
                    <div>
                      <span>Decision</span>
                      <strong>{resolvedOpportunity.evidence.decision}</strong>
                    </div>
                    <div>
                      <span>{structureLabel}</span>
                      <strong>{formatPrice(resolvedOpportunity.evidence.resistance)}</strong>
                    </div>
                    <div>
                      <span>Breakout</span>
                      <strong>
                        {
                          formatBarRef(
                            resolvedOpportunity.evidence.breakout_candle_index,
                            resolvedOpportunity.evidence.breakout_candle_time,
                          ).bar
                        }
                        <small className="kv-sub">
                          {
                            formatBarRef(
                              resolvedOpportunity.evidence.breakout_candle_index,
                              resolvedOpportunity.evidence.breakout_candle_time,
                            ).when
                          }
                        </small>
                      </strong>
                    </div>
                    <div>
                      <span>Retest</span>
                      <strong>
                        {
                          formatBarRef(
                            resolvedOpportunity.evidence.retest_candle_index,
                            resolvedOpportunity.evidence.retest_candle_time,
                          ).bar
                        }
                        <small className="kv-sub">
                          {
                            formatBarRef(
                              resolvedOpportunity.evidence.retest_candle_index,
                              resolvedOpportunity.evidence.retest_candle_time,
                            ).when
                          }
                        </small>
                      </strong>
                    </div>
                    <div>
                      <span>Confirmation</span>
                      <strong>
                        {
                          formatBarRef(
                            resolvedOpportunity.evidence.confirmation_candle_index,
                            resolvedOpportunity.evidence.confirmation_candle_time,
                          ).bar
                        }
                        <small className="kv-sub">
                          {
                            formatBarRef(
                              resolvedOpportunity.evidence.confirmation_candle_index,
                              resolvedOpportunity.evidence.confirmation_candle_time,
                            ).when
                          }
                        </small>
                      </strong>
                    </div>
                    <div>
                      <span>ATR</span>
                      <strong>{formatNumber(resolvedOpportunity.evidence.atr_value, 2)}</strong>
                    </div>
                    <div>
                      <span>Volume SMA</span>
                      <strong>{formatVolume(resolvedOpportunity.evidence.volume_sma_value)}</strong>
                    </div>
                    <div>
                      <span>{isShort ? 'Breakdown volume' : 'Breakout volume'}</span>
                      <strong>{formatVolume(resolvedOpportunity.evidence.breakout_volume)}</strong>
                    </div>
                    <div>
                      <span>{retestLabel}</span>
                      <strong>{formatPrice(resolvedOpportunity.evidence.retest_low)}</strong>
                    </div>
                    <div>
                      <span>Confirmation volume</span>
                      <strong>{formatVolume(resolvedOpportunity.evidence.confirmation_volume)}</strong>
                    </div>
                  </div>
                </section>
              )}

              {forming && (
                <section className="detail-block">
                  <h3>Almost ready</h3>
                  <div className="kv-grid">
                    <div>
                      <span>Stage</span>
                      <strong>{formingStageLabel(forming.stage)}</strong>
                    </div>
                    <div>
                      <span>{structureLabel}</span>
                      <strong>{formatPrice(forming.resistance)}</strong>
                    </div>
                    <div>
                      <span>Current price</span>
                      <strong className={`live-tick ${priceFlash ? `flash-${priceFlash}` : ''}`}>
                        {formatPrice(forming.current_price)}
                      </strong>
                    </div>
                    <div>
                      <span>Change</span>
                      <strong className={valueClass(forming.current_price_change_percent ?? 0)}>
                        {formatPercent(forming.current_price_change_percent)}
                      </strong>
                    </div>
                    <div>
                      <span>Bars remaining</span>
                      <strong>{forming.bars_remaining}</strong>
                    </div>
                    <div>
                      <span>Why</span>
                      <strong>{forming.reason}</strong>
                    </div>
                  </div>
                </section>
              )}

              {setupLoading && <p className="detail-loading">Loading trade plan…</p>}
              {!setupLoading && setupStatus && !resolvedOpportunity && !forming && (
                <div className="empty-state">
                  <strong>No confirmed setup</strong>
                  <span>{setupStatus}</span>
                </div>
              )}
              {!setupLoading && !setupStatus && !resolvedOpportunity && !forming && (
                <div className="empty-state">
                  <strong>No active setup</strong>
                  <span>No confirmed trade plan for the current date range.</span>
                </div>
              )}
            </div>
          )}

          {activeTab === 'technical' && technical && (
            <div className="detail-stack">
              <section className="detail-block">
                <div className="detail-block-head">
                  <h3>Key technicals</h3>
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() => {
                      setDraftIndicators(
                        visibleIndicators.length > 0
                          ? [...visibleIndicators]
                          : [...DEFAULT_VISIBLE_INDICATORS],
                      )
                      setCustomizeOpen((open) => !open)
                    }}
                  >
                    {customizeOpen ? 'Hide list' : 'Customize'}
                  </button>
                </div>
                {customizeOpen && (
                  <div className="tech-customize-panel">
                    <ul className="tech-customize-list">
                      {allIndicatorNames.map((name) => (
                        <li key={name}>
                          <label>
                            <input
                              type="checkbox"
                              checked={draftIndicators.includes(name)}
                              onChange={() =>
                                setDraftIndicators((current) =>
                                  current.includes(name)
                                    ? current.filter((item) => item !== name)
                                    : [...current, name],
                                )
                              }
                            />
                            <span>{name}</span>
                          </label>
                        </li>
                      ))}
                    </ul>
                    <div className="tech-customize-actions">
                      <button
                        type="button"
                        onClick={() => {
                          const next =
                            draftIndicators.length > 0
                              ? draftIndicators
                              : [...DEFAULT_VISIBLE_INDICATORS]
                          setVisibleIndicators(next)
                          window.localStorage.setItem(TECH_VISIBLE_KEY, JSON.stringify(next))
                          setCustomizeOpen(false)
                        }}
                      >
                        Save
                      </button>
                      <button type="button" className="ghost-btn" onClick={() => setCustomizeOpen(false)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                <div className="metric-row">
                  {filteredIndicators.map((item) => (
                    <div key={item.name} className={`metric-tile signal-${item.signal}`}>
                      <span>{item.name}</span>
                      <strong>{item.value == null ? '—' : formatNumber(item.value, 2)}</strong>
                      <em>{item.signal}</em>
                    </div>
                  ))}
                </div>
                {filteredIndicators.length === 0 && (
                  <p className="field-hint">No indicators selected. Use Customize to show some.</p>
                )}
              </section>
              {technical.pivots && (
                <section className="detail-block">
                  <h3>Pivot points</h3>
                  <div className="kv-grid">
                    <div>
                      <span>Pivot</span>
                      <strong>{formatPrice(technical.pivots.pivot)}</strong>
                    </div>
                    <div>
                      <span>R1 / R2 / R3</span>
                      <strong>
                        {formatPrice(technical.pivots.resistance_1)} /{' '}
                        {formatPrice(technical.pivots.resistance_2)} /{' '}
                        {formatPrice(technical.pivots.resistance_3)}
                      </strong>
                    </div>
                    <div>
                      <span>S1 / S2 / S3</span>
                      <strong>
                        {formatPrice(technical.pivots.support_1)} /{' '}
                        {formatPrice(technical.pivots.support_2)} /{' '}
                        {formatPrice(technical.pivots.support_3)}
                      </strong>
                    </div>
                  </div>
                </section>
              )}
            </div>
          )}

          {activeTab === 'fno' && (
            <div className="fno-panel">
              <div className="fno-toolbar">
                <div>
                  <p className="fno-toolbar-title">Futures & options</p>
                  <p className="fno-toolbar-sub">Near-ATM strikes for the selected expiry</p>
                </div>
                <label className="fno-expiry-field" htmlFor="fno-expiry">
                  <span>Expiry</span>
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
                </label>
              </div>

              {fno && fno.status !== 'ok' && (
                <div className="empty-state">
                  <strong>F&O unavailable</strong>
                  <span>{fno.detail || 'Option chain could not be loaded for this symbol.'}</span>
                </div>
              )}

              {fno && fno.status === 'ok' && (
                <>
                  <div className="fno-stats">
                    <div className="fno-stat">
                      <span>Spot</span>
                      <strong>{formatPrice(fno.spot)}</strong>
                    </div>
                    <div className="fno-stat">
                      <span>PCR</span>
                      <strong>{formatNumber(fno.pcr, 2)}</strong>
                    </div>
                    <div className="fno-stat">
                      <span>Contract expiry</span>
                      <strong>{fno.expiry || '—'}</strong>
                    </div>
                  </div>

                  <div className="fno-chain">
                    <div className="fno-chain-legend">
                      <span className="fno-legend-call">Calls</span>
                      <span className="fno-legend-strike">Strike</span>
                      <span className="fno-legend-put">Puts</span>
                    </div>
                    <div className="table-wrap fno-chain-scroll">
                      <table className="fno-chain-table">
                        <thead>
                          <tr>
                            <th className="col-call">LTP</th>
                            <th className="col-call">OI</th>
                            <th className="col-call">IV</th>
                            <th className="col-strike">Strike</th>
                            <th className="col-put">IV</th>
                            <th className="col-put">OI</th>
                            <th className="col-put">LTP</th>
                          </tr>
                        </thead>
                        <tbody>
                          {atmRows.map((row) => {
                            const isAtm = atmStrike != null && String(row.strike) === String(atmStrike)
                            return (
                              <tr key={String(row.strike)} className={isAtm ? 'is-atm' : undefined}>
                                <td className="col-call num-cell">{formatPrice(row.call_ltp)}</td>
                                <td className="col-call num-cell">{formatNumber(row.call_oi, 0)}</td>
                                <td className="col-call num-cell">{formatNumber(row.call_iv, 1)}</td>
                                <td className="col-strike">
                                  <span className="strike-value">{formatNumber(row.strike, 0)}</span>
                                  {isAtm ? <em className="atm-pill">ATM</em> : null}
                                </td>
                                <td className="col-put num-cell">{formatNumber(row.put_iv, 1)}</td>
                                <td className="col-put num-cell">{formatNumber(row.put_oi, 0)}</td>
                                <td className="col-put num-cell">{formatPrice(row.put_ltp)}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === 'news' && news && (
            <div className="news-panel">
              {news.status !== 'ok' && (
                <div className="empty-state">
                  <strong>News feed unavailable</strong>
                  <span>{news.detail || 'NSE announcements could not be loaded right now.'}</span>
                </div>
              )}

              <div className="news-columns">
                <section className="news-column">
                  <header className="news-column-head">
                    <h3>Announcements</h3>
                    <span>{news.announcements.length}</span>
                  </header>
                  {news.announcements.length === 0 ? (
                    <p className="field-hint">No recent announcements.</p>
                  ) : (
                    <ul className="news-card-list">
                      {news.announcements.map((item) => (
                        <li key={`${item.title}-${item.published_at}`}>
                          {item.url ? (
                            <a className="news-card-link" href={item.url} target="_blank" rel="noreferrer">
                              {item.title}
                            </a>
                          ) : (
                            <strong className="news-card-title">{item.title}</strong>
                          )}
                          <div className="news-card-meta">
                            <span>{item.source || 'NSE'}</span>
                            <span>{item.published_at ? formatDateTime(item.published_at) : '—'}</span>
                            {item.category ? <em>{item.category}</em> : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="news-column">
                  <header className="news-column-head">
                    <h3>Events</h3>
                    <span>{news.events.length}</span>
                  </header>
                  {news.events.length === 0 ? (
                    <p className="field-hint">No upcoming corporate actions found.</p>
                  ) : (
                    <ul className="news-card-list">
                      {news.events.map((item) => (
                        <li key={`${item.title}-${item.published_at}`}>
                          <strong className="news-card-title">{item.title}</strong>
                          <div className="news-card-meta">
                            <span>{item.category || 'Event'}</span>
                            <span>{item.published_at || '—'}</span>
                            {item.source ? <em>{item.source}</em> : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
