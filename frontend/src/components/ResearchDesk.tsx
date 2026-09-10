import { useEffect, useMemo, useRef, useState } from 'react'
import { SetupChart, type ChartCandle } from './SetupChart'
import { LiveValue } from './LiveValue'
import { directionLabel } from '../terminology'
import { buildBacktestInterpreter } from '../coach/backtestInterpreter'
import { CompareNamesDesk } from './CompareNamesDesk'

type Tab = 'overview' | 'technical' | 'fundamentals' | 'news' | 'fno' | 'similar' | 'compare' | 'evaluate'

type OverviewPayload = {
  symbol: string
  last_close?: string | number | null
  last_volume?: number | null
  high_52w?: string | number | null
  low_52w?: string | number | null
  current_price?: string | number | null
  current_price_change_percent?: string | number | null
  sector?: string | null
  caution_flags?: string[]
  quality_flags?: string[]
  quality_checks?: {
    id: string
    label: string
    status: string
    detail: string
  }[]
  caution_summary?: string | null
  range_52w_position_pct?: string | number | null
  fa_proxies?: {
    label: string
    value?: string | null
    change_percent?: string | number | null
    available?: boolean
    note?: string | null
  }[]
  performance?: { label: string; change_percent?: string | number | null }[]
  candle_count?: number
}

type TechnicalPayload = {
  symbol: string
  last_close?: string | number | null
  indicators?: { name: string; value?: string | number | null; signal: string; detail: string }[]
  pivots?: {
    pivot: string | number
    resistance_1: string | number
    resistance_2: string | number
    support_1: string | number
    support_2: string | number
  } | null
  volume_vs_sma?: string | number | null
  support?: string | number | null
  resistance?: string | number | null
  trendline?: string | number | null
  atr?: string | number | null
  swing_fit?: string | null
  swing_eligible?: boolean
  orb_snapshot?: string | number | null
  orb_high?: string | number | null
  orb_low?: string | number | null
  orb_armed?: boolean
  orb_status?: string | null
}

type NewsPayload = {
  announcements?: { title: string; published_at?: string | null; source: string; category: string; url?: string | null }[]
  events?: { title: string; published_at?: string | null; source: string; category: string; url?: string | null }[]
  corporate_actions?: {
    symbol: string
    ex_date: string
    type: string
    block_sessions?: number
    end_date?: string | null
    source?: string
    label?: string | null
  }[]
  trading_caution?: boolean
  caution_summary?: string | null
  status?: string
  detail?: string | null
}

type FnoPayload = {
  symbol?: string
  spot?: string | number | null
  pcr?: string | number | null
  expiry?: string | null
  expiry_date?: string
  futures_ltp?: string | number | null
  futures_premium?: string | number | null
  futures_premium_status?: string | null
  oi_change?: string | number | null
  call_oi_change?: string | number | null
  put_oi_change?: string | number | null
  oi_change_status?: string | null
  call_wall_strike?: string | number | null
  put_wall_strike?: string | number | null
  call_wall_oi?: string | number | null
  put_wall_oi?: string | number | null
  rows?: {
    strike?: string | number | null
    call_ltp?: string | number | null
    call_oi?: string | number | null
    call_oi_change?: string | number | null
    call_iv?: string | number | null
    put_ltp?: string | number | null
    put_oi?: string | number | null
    put_oi_change?: string | number | null
    put_iv?: string | number | null
  }[]
  status?: string
  detail?: string | null
}

type SimilarItem = {
  symbol: string
  direction?: string
  confirmation_time: string
  distance?: number
  quality_score?: string | number | null
  atr_percent?: string | number | null
  risk_reward_ratio?: string | number | null
  entry_price?: string | number | null
  stop_loss?: string | number | null
  target?: string | number | null
  setup_name?: string | null
  forward_return_pct?: string | number | null
  forward_bars?: number | null
  blurb?: string | null
}

type SimilarMeta = {
  direction?: string | null
  setup_family?: string | null
  detail?: string | null
  query_source?: string | null
}

type StrategyEval = {
  has_setup: boolean
  status: string
  reason?: string | null
  candidate?: {
    direction: string
    entry_price: string | number
    stop_loss: string | number
    target: string | number
    risk_reward_ratio: string | number
    setup_name: string
  } | null
  evidence?: {
    resistance: string | number
    breakout_candle_index: number
    retest_candle_index: number
    confirmation_candle_index: number
    decision: string
    atr_value?: string | number
    structure_label?: string | null
  } | null
}

type BacktestResult = {
  completed_trades?: number
  metrics: {
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: string | number
    total_pnl: string | number
    average_r: string | number
    maximum_drawdown: string | number
  }
  interpretation?: string | null
  interpretation_provider?: string | null
}

type Insight = {
  title: string
  headline?: string | null
  bullets: string[]
  provider: string
}

type Props = {
  baseUrl: string
  initialSymbol?: string | null
  accountEquity: string
  riskPercent: string
  formatPrice: (value: string | number | null | undefined) => string
  formatNumber: (value: string | number | null | undefined, digits?: number) => string
  formatPercent: (value: string | number | null | undefined) => string
  formatVolume: (value: string | number | null | undefined) => string
  formatDateTime: (value: string | null | undefined) => string
  valueClass: (value: string | number) => string
  onOpenEligibility?: () => void
  onOpenFilters?: () => void
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'technical', label: 'Technical' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'news', label: 'News Events' },
  { id: 'fno', label: 'F&O' },
  { id: 'similar', label: 'Similar' },
  { id: 'compare', label: 'Compare' },
  { id: 'evaluate', label: 'Evaluate' },
]

function defaultRange() {
  const end = new Date()
  const start = new Date()
  start.setUTCDate(start.getUTCDate() - 400)
  return { start, end }
}

function toDateInputValue(date: Date) {
  return date.toISOString().slice(0, 10)
}

function rangeFromInputs(startDate: string, endDate: string) {
  const start = new Date(`${startDate}T00:00:00.000Z`)
  const end = new Date(`${endDate}T23:59:59.999Z`)
  return { start, end }
}

function formatApiDetail(detail: unknown, fallback: string): string {
  if (detail == null) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg: unknown }).msg)
        return JSON.stringify(item)
      })
      .filter(Boolean)
      .join('; ') || fallback
  }
  if (typeof detail === 'object' && detail && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  try {
    return JSON.stringify(detail)
  } catch {
    return fallback
  }
}

function interpretationBullets(text: string | null | undefined, symbol: string, metrics?: {
  win_rate?: string | number | null
  total_trades?: number | null
  average_r?: string | number | null
  maximum_drawdown?: string | number | null
} | null): { bullets: string[]; refused: string } {
  return buildBacktestInterpreter(symbol, metrics || null, text)
}

function fitFromTechnical(tech: TechnicalPayload | null, evalResult: StrategyEval | null) {
  if (evalResult?.has_setup && evalResult.candidate) {
    const dir = evalResult.candidate.direction === 'SHORT' ? 'Bearish breakdown' : 'Bullish continuation'
    const rr = Number(evalResult.candidate.risk_reward_ratio)
    const fit = Number.isFinite(rr) && rr >= 2 ? 'High' : 'Moderate'
    const criteria = [
      evalResult.evidence?.structure_label || evalResult.evidence?.decision || 'Structure confirmed',
      `R:R ${Number.isFinite(rr) ? rr.toFixed(2) : '—'}`,
      evalResult.candidate.setup_name,
    ]
    return { title: `${dir} setup`, fit, criteria, ok: true, tone: 'ok' as const }
  }
  if (!tech?.indicators?.length) {
    return {
      title: 'No technical snapshot yet',
      fit: '—',
      criteria: ['Load a symbol with candle history'],
      ok: false,
      tone: 'idle' as const,
    }
  }
  const signals = tech.indicators.map((i) => i.signal.toUpperCase())
  const bullish = signals.filter((s) => s.includes('BULL') || s.includes('BUY') || s.includes('UP')).length
  const bearish = signals.filter((s) => s.includes('BEAR') || s.includes('SELL') || s.includes('DOWN')).length
  const title =
    bullish > bearish ? 'Bias leaning bullish' : bearish > bullish ? 'Bias leaning bearish' : 'Mixed technical picture'
  const fit = Math.abs(bullish - bearish) >= 2 ? 'Moderate' : 'Low'
  const criteria = tech.indicators.slice(0, 4).map((i) => `${i.name}: ${i.signal}`)
  const tone = fit === 'Moderate' ? ('mid' as const) : ('low' as const)
  return { title, fit, criteria, ok: false, tone }
}

function FitStatusMark({ tone }: { tone: 'ok' | 'mid' | 'low' | 'idle' }) {
  return (
    <div className={`research-fit-mark is-${tone}`} aria-hidden="true">
      {tone === 'ok' ? (
        <svg viewBox="0 0 24 24" className="research-fit-svg" fill="none" stroke="currentColor" strokeWidth="2.4">
          <path d="M5 12.5l4.2 4.2L19 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : tone === 'mid' ? (
        <svg viewBox="0 0 24 24" className="research-fit-svg" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M5 12h14" strokeLinecap="round" />
          <path d="M8 8l-3 4 3 4M16 8l3 4-3 4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : tone === 'low' ? (
        <svg viewBox="0 0 24 24" className="research-fit-svg" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M8 8l8 8M16 8l-8 8" strokeLinecap="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="research-fit-svg" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3.5" />
        </svg>
      )}
    </div>
  )
}

/** Compact outline badge icon for Technical Panel swing-fit row. */
function SwingFitIcon({ level }: { level: string }) {
  const tone =
    level === 'High' ? 'high' : level === 'Moderate' ? 'moderate' : level === 'Low' ? 'low' : 'idle'
  return (
    <svg
      className={`research-swing-fit-ico is-${tone}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      {tone === 'high' ? (
        <path d="M8 12.2l2.6 2.6L16.4 9" strokeLinecap="round" strokeLinejoin="round" />
      ) : tone === 'moderate' ? (
        <path d="M8 12h8" strokeLinecap="round" />
      ) : tone === 'low' ? (
        <path d="M9 9l6 6M15 9l-6 6" strokeLinecap="round" />
      ) : (
        <circle cx="12" cy="12" r="2.25" fill="currentColor" stroke="none" />
      )}
    </svg>
  )
}

type CaAction = {
  symbol: string
  ex_date: string
  type: string
  block_sessions?: number
  end_date?: string | null
  source?: string
  label?: string | null
}

function parseDateOnly(value: string | null | undefined): Date | null {
  if (!value) return null
  const text = String(value).slice(0, 10)
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  if (!match) {
    const fallback = new Date(value)
    return Number.isNaN(fallback.getTime()) ? null : fallback
  }
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
}

function monthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

function buildMonthCells(year: number, monthIndex: number) {
  const first = new Date(year, monthIndex, 1)
  const startPad = first.getDay()
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate()
  const cells: ({ day: number; date: Date } | null)[] = []
  for (let i = 0; i < startPad; i += 1) cells.push(null)
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({ day, date: new Date(year, monthIndex, day) })
  }
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

function actionsForDay(actions: CaAction[], day: Date) {
  const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
  return actions.filter((action) => {
    const start = parseDateOnly(action.ex_date)
    const end = parseDateOnly(action.end_date || action.ex_date)
    if (!start || !end) return false
    const startKey = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`
    const endKey = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}`
    return key >= startKey && key <= endKey
  })
}

function isHttpUrl(url: string | null | undefined): boolean {
  if (!url) return false
  const text = url.trim().toLowerCase()
  return text.startsWith('http://') || text.startsWith('https://')
}

function formatCaDate(value: string | null | undefined): string {
  const d = parseDateOnly(value)
  if (!d) return value || '—'
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(d)
}

function formatNewsWhen(
  value: string | null | undefined,
  formatDateTime: (value: string | null | undefined) => string,
): string {
  if (!value) return ''
  const nse = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?/.exec(value.trim())
  if (nse) {
    const day = nse[1].padStart(2, '0')
    return nse[4] ? `${day} ${nse[2]} ${nse[3]} · ${nse[4]}` : `${day} ${nse[2]} ${nse[3]}`
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) return formatCaDate(value)
  return formatDateTime(value)
}

function caChipLabel(action: CaAction): string {
  const base = action.label || action.type || 'CA'
  if ((action.block_sessions || 1) > 1) return `${base} CA Day Block`
  return base
}

function formatSetupFamily(name: string | null | undefined): string {
  if (!name) return '—'
  return name.replace(/Confirmation$/i, '').replace(/_/g, '') || name
}

function ChangeChip({
  value,
  formatPercent,
  valueClass,
}: {
  value: string | number
  formatPercent: (value: string | number | null | undefined) => string
  valueClass: (value: string | number) => string
}) {
  const numeric = Number(value)
  const sign = Number.isFinite(numeric) && numeric > 0 ? '+' : ''
  return (
    <span className={`research-chg-chip ${valueClass(value)}`}>
      {sign}
      {formatPercent(value)}
    </span>
  )
}


export function ResearchDesk({
  baseUrl,
  initialSymbol,
  accountEquity,
  riskPercent,
  formatPrice,
  formatNumber,
  formatPercent,
  formatVolume,
  formatDateTime,
  valueClass,
  onOpenEligibility,
  onOpenFilters,
}: Props) {
  const [symbol, setSymbol] = useState(() => (initialSymbol || 'RELIANCE').trim().toUpperCase())
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(false)
  const [evalLoading, setEvalLoading] = useState(false)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [error, setError] = useState('')
  const [overview, setOverview] = useState<OverviewPayload | null>(null)
  const [technical, setTechnical] = useState<TechnicalPayload | null>(null)
  const [news, setNews] = useState<NewsPayload | null>(null)
  const [fno, setFno] = useState<FnoPayload | null>(null)
  const [similar, setSimilar] = useState<SimilarItem[]>([])
  const [similarMeta, setSimilarMeta] = useState<SimilarMeta | null>(null)
  const [compareSelected, setCompareSelected] = useState<string[]>([])
  const [compareLeft, setCompareLeft] = useState('RELIANCE')
  const [compareRight, setCompareRight] = useState('TCS')
  const [insight, setInsight] = useState<Insight | null>(null)
  const [candles, setCandles] = useState<ChartCandle[]>([])
  const [evalResult, setEvalResult] = useState<StrategyEval | null>(null)
  const [backtest, setBacktest] = useState<BacktestResult | null>(null)
  const [loadedSymbol, setLoadedSymbol] = useState('')
  const [suggestions, setSuggestions] = useState<{ symbol: string; asset_class?: string }[]>([])
  const [suggestOpen, setSuggestOpen] = useState(false)
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [activeSuggest, setActiveSuggest] = useState(-1)
  const [caMonth, setCaMonth] = useState(() => new Date())
  const [fnoExpiry, setFnoExpiry] = useState('current_month')
  const [evalStartDate, setEvalStartDate] = useState(() => toDateInputValue(defaultRange().start))
  const [evalEndDate, setEvalEndDate] = useState(() => toDateInputValue(defaultRange().end))
  const [evalStrategy] = useState('BreakoutRetest')
  const [actionStatus, setActionStatus] = useState('')
  const searchWrapRef = useRef<HTMLDivElement | null>(null)
  const suggestSeq = useRef(0)
  const caMonthSynced = useRef(false)

  useEffect(() => {
    const next = (initialSymbol || '').trim().toUpperCase()
    if (next && next !== symbol) setSymbol(next)
    // Only sync when parent hands off a new symbol.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol])

  useEffect(() => {
    function onDocMouseDown(event: MouseEvent) {
      if (!searchWrapRef.current?.contains(event.target as Node)) {
        setSuggestOpen(false)
        setActiveSuggest(-1)
      }
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [])

  useEffect(() => {
    const q = symbol.trim().toUpperCase()
    if (q.length < 1) {
      setSuggestions([])
      setSuggestOpen(false)
      setActiveSuggest(-1)
      return
    }
    if (loadedSymbol && q === loadedSymbol) {
      setSuggestions([])
      setSuggestOpen(false)
      setActiveSuggest(-1)
      return
    }
    const seq = ++suggestSeq.current
    const timer = window.setTimeout(() => {
      setSuggestLoading(true)
      void fetch(
        `${baseUrl}/api/v1/universe/symbols?q=${encodeURIComponent(q)}&limit=12&universe=NSE_ALL`,
      )
        .then(async (res) => {
          if (!res.ok) throw new Error('suggest failed')
          return (await res.json()) as { symbols?: { symbol: string; asset_class?: string }[] }
        })
        .then((payload) => {
          if (seq !== suggestSeq.current) return
          const rows = payload.symbols || []
          setSuggestions(rows)
          setSuggestOpen(rows.length > 0)
          setActiveSuggest(rows.length ? 0 : -1)
        })
        .catch(() => {
          if (seq !== suggestSeq.current) return
          setSuggestions([])
          setSuggestOpen(false)
          setActiveSuggest(-1)
        })
        .finally(() => {
          if (seq === suggestSeq.current) setSuggestLoading(false)
        })
    }, 180)
    return () => window.clearTimeout(timer)
  }, [symbol, baseUrl, loadedSymbol])

  function pickSuggestion(next: string) {
    const sym = next.trim().toUpperCase()
    if (!sym) return
    setSymbol(sym)
    setSuggestOpen(false)
    setSuggestions([])
    setActiveSuggest(-1)
    void load(sym)
  }

  async function load(symOverride?: string) {
    const sym = (symOverride ?? symbol).trim().toUpperCase()
    if (!sym) return
    setSuggestOpen(false)
    setSuggestions([])
    setActiveSuggest(-1)
    setSymbol(sym)
    setLoading(true)
    setError('')
    setBacktest(null)
    try {
      const { start, end } = defaultRange()
      const rangeQuery = `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`
      const [
        overviewRes,
        technicalRes,
        newsRes,
        fnoRes,
        similarRes,
        candlesRes,
        insightRes,
        evalRes,
      ] = await Promise.all([
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/overview?${rangeQuery}`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/technical?${rangeQuery}`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/news-events`),
        fetch(
          `${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/fno?expiry=${encodeURIComponent(fnoExpiry)}`,
        ),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/similar-setups?limit=6`),
        fetch(`${baseUrl}/api/v1/market-data/candles/${encodeURIComponent(sym)}?timeframe=1d&${rangeQuery}`),
        fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/insight`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tab: 'overview', context: { symbol: sym } }),
        }),
        fetch(`${baseUrl}/api/v1/strategy/evaluate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: sym,
            timeframe: '1d',
            start: start.toISOString(),
            end: end.toISOString(),
          }),
        }),
      ])

      if (!overviewRes.ok && !technicalRes.ok) {
        throw new Error('Failed to load research for this symbol')
      }

      const ov = overviewRes.ok ? ((await overviewRes.json()) as OverviewPayload) : null
      const tech = technicalRes.ok ? ((await technicalRes.json()) as TechnicalPayload) : null
      const newsPayload = newsRes.ok ? ((await newsRes.json()) as NewsPayload) : null
      const fnoPayload = fnoRes.ok ? ((await fnoRes.json()) as FnoPayload) : null
      const similarPayload = similarRes.ok
        ? ((await similarRes.json()) as {
            matches?: SimilarItem[]
            items?: SimilarItem[]
            setups?: SimilarItem[]
            direction?: string | null
            setup_family?: string | null
            detail?: string | null
            query_source?: string | null
          })
        : null
      const candlePayload = candlesRes.ok ? await candlesRes.json() : []
      const insightPayload = insightRes.ok ? ((await insightRes.json()) as Insight) : null
      const strategyPayload = evalRes.ok ? ((await evalRes.json()) as StrategyEval) : null

      setOverview(ov)
      setTechnical(tech)
      setNews(newsPayload)
      setFno(fnoPayload)
      setSimilar(similarPayload?.matches || similarPayload?.items || similarPayload?.setups || [])
      setSimilarMeta(
        similarPayload
          ? {
              direction: similarPayload.direction,
              setup_family: similarPayload.setup_family,
              detail: similarPayload.detail,
              query_source: similarPayload.query_source,
            }
          : null,
      )
      setCompareSelected([])
      setCandles(Array.isArray(candlePayload) ? candlePayload : [])
      setInsight(insightPayload)
      setEvalResult(strategyPayload)
      setLoadedSymbol(sym)
      caMonthSynced.current = false
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Research failed')
      setOverview(null)
      setTechnical(null)
      setNews(null)
      setFno(null)
      setSimilar([])
      setSimilarMeta(null)
      setCompareSelected([])
      setCandles([])
      setInsight(null)
      setEvalResult(null)
      setLoadedSymbol('')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load(symbol)
    // Initial + when parent forces a new initialSymbol via state sync above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl])

  useEffect(() => {
    if (!initialSymbol) return
    const next = initialSymbol.trim().toUpperCase()
    if (next && next !== loadedSymbol) void load(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol])

  useEffect(() => {
    if (!loadedSymbol || tab !== 'fno') return
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(
          `${baseUrl}/api/v1/research/${encodeURIComponent(loadedSymbol)}/fno?expiry=${encodeURIComponent(fnoExpiry)}`,
        )
        if (!res.ok || cancelled) return
        const payload = (await res.json()) as FnoPayload
        if (!cancelled) setFno(payload)
      } catch {
        /* keep prior chain */
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fnoExpiry])

  async function runEvaluate() {
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    setEvalLoading(true)
    setError('')
    setActionStatus(`Running evaluate for ${sym}…`)
    try {
      const { start, end } = rangeFromInputs(evalStartDate, evalEndDate)
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
        throw new Error('Date range is invalid')
      }
      const rangeQuery = `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`
      const [response, candlesRes] = await Promise.all([
        fetch(`${baseUrl}/api/v1/strategy/evaluate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: sym,
            timeframe: '1d',
            start: start.toISOString(),
            end: end.toISOString(),
          }),
        }),
        fetch(
          `${baseUrl}/api/v1/market-data/candles/${encodeURIComponent(sym)}?timeframe=1d&${rangeQuery}`,
        ),
      ])
      if (!response.ok) {
        let detail: unknown = 'Evaluate failed'
        try {
          const payload = await response.json()
          detail = payload.detail ?? payload.message ?? detail
        } catch {
          /* ignore */
        }
        throw new Error(formatApiDetail(detail, 'Evaluate failed'))
      }
      const result = (await response.json()) as StrategyEval
      setEvalResult(result)
      setLoadedSymbol(sym)
      if (candlesRes.ok) {
        const candlePayload = await candlesRes.json()
        setCandles(Array.isArray(candlePayload) ? candlePayload : [])
      }
      if (result.has_setup && result.candidate) {
        setActionStatus(
          `Evaluate complete · ${result.status} · ${directionLabel(result.candidate.direction)} · Entry ${formatPrice(result.candidate.entry_price)}`,
        )
      } else {
        setActionStatus(
          `Evaluate complete · ${result.status}${result.reason ? ` — ${result.reason}` : ''}`,
        )
      }
    } catch (err) {
      setActionStatus('')
      setError(err instanceof Error ? err.message : 'Evaluate failed')
    } finally {
      setEvalLoading(false)
    }
  }

  async function runBacktest() {
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    setBacktestLoading(true)
    setError('')
    setActionStatus(`Running backtest for ${sym}…`)
    try {
      const { start, end } = rangeFromInputs(evalStartDate, evalEndDate)
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
        throw new Error('Date range is invalid')
      }
      const response = await fetch(`${baseUrl}/api/v1/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: sym,
          timeframe: '1d',
          start: start.toISOString(),
          end: end.toISOString(),
          account_equity: accountEquity || '100000',
          risk_percent: riskPercent || '1',
          slippage_per_share: '0.05',
          cost_per_trade: '20',
        }),
      })
      if (!response.ok) {
        let detail: unknown = 'Backtest failed'
        try {
          const payload = await response.json()
          detail = payload.detail ?? payload.message ?? detail
        } catch {
          /* ignore */
        }
        throw new Error(formatApiDetail(detail, 'Backtest failed'))
      }
      const result = (await response.json()) as BacktestResult
      setBacktest(result)
      setLoadedSymbol(sym)
      const trades = result.metrics?.total_trades ?? result.completed_trades ?? 0
      setActionStatus(
        `Backtest complete · ${trades} trade${Number(trades) === 1 ? '' : 's'} · win ${formatPercent(result.metrics.win_rate)} · Avg R ${formatNumber(result.metrics.average_r, 2)}`,
      )
    } catch (err) {
      setActionStatus('')
      setError(err instanceof Error ? err.message : 'Backtest failed')
      setBacktest(null)
    } finally {
      setBacktestLoading(false)
    }
  }

  const chartLevels = useMemo(() => {
    const c = evalResult?.candidate
    if (!c) return {}
    const isShort = c.direction === 'SHORT'
    return {
      resistance: isShort ? null : evalResult?.evidence?.resistance ?? null,
      support: isShort ? evalResult?.evidence?.resistance ?? null : null,
      entry: c.entry_price,
      stop: c.stop_loss,
      target: c.target,
      breakoutIndex: evalResult?.evidence?.breakout_candle_index,
      retestIndex: evalResult?.evidence?.retest_candle_index,
      confirmationIndex: evalResult?.evidence?.confirmation_candle_index,
    }
  }, [evalResult])

  const structureLevels = useMemo(
    () => ({
      support: technical?.support ?? technical?.pivots?.support_1 ?? null,
      resistance: technical?.resistance ?? technical?.pivots?.resistance_1 ?? null,
      trendline: technical?.trendline ?? null,
    }),
    [technical],
  )

  const corporateActions = news?.corporate_actions || []

  useEffect(() => {
    if (caMonthSynced.current || !corporateActions.length) return
    const today = new Date()
    let best: Date | null = null
    let bestDist = Number.POSITIVE_INFINITY
    for (const action of corporateActions) {
      const d = parseDateOnly(action.ex_date)
      if (!d) continue
      const dist = Math.abs(d.getTime() - today.getTime())
      if (dist < bestDist) {
        bestDist = dist
        best = d
      }
    }
    if (best) {
      setCaMonth(new Date(best.getFullYear(), best.getMonth(), 1))
      caMonthSynced.current = true
    }
  }, [corporateActions])

  const caCells = useMemo(
    () => buildMonthCells(caMonth.getFullYear(), caMonth.getMonth()),
    [caMonth],
  )

  const monthActions = useMemo(() => {
    const key = monthKey(caMonth)
    return corporateActions.filter((action) => {
      const start = parseDateOnly(action.ex_date)
      const end = parseDateOnly(action.end_date || action.ex_date)
      if (!start || !end) return false
      const startKey = monthKey(start)
      const endKey = monthKey(end)
      return key >= startKey && key <= endKey
    })
  }, [caMonth, corporateActions])

  const newsCards = useMemo(() => {
    const rows = [
      ...(news?.announcements || []).map((item) => ({ ...item, kind: 'announcement' as const })),
      ...(news?.events || []).map((item) => ({ ...item, kind: 'event' as const })),
    ]
    return rows.slice(0, 16)
  }, [news])

  const swingEligible = Boolean(evalResult?.has_setup || technical?.swing_eligible)
  const fit = fitFromTechnical(technical, evalResult)
  const swingFitLabel =
    evalResult?.has_setup && evalResult.candidate
      ? Number(evalResult.candidate.risk_reward_ratio) >= 2
        ? 'High'
        : 'Moderate'
      : technical?.swing_fit || fit.fit

  const atrValue =
    technical?.atr ??
    technical?.indicators?.find((row) => row.name.startsWith('ATR'))?.value ??
    null

  const flags = overview?.caution_flags?.length ? overview.caution_flags : []
  const displaySym = loadedSymbol || symbol || '—'

  const atmStrike = useMemo(() => {
    if (!fno?.rows?.length || fno.spot == null) return null
    const spot = Number(fno.spot)
    if (!Number.isFinite(spot)) return null
    let best: string | number | null = null
    let bestDiff = Number.POSITIVE_INFINITY
    for (const row of fno.rows) {
      if (row.strike == null) continue
      const diff = Math.abs(Number(row.strike) - spot)
      if (diff < bestDiff) {
        bestDiff = diff
        best = row.strike
      }
    }
    return best
  }, [fno])

  const fnoRows = useMemo(() => {
    if (!fno?.rows?.length) return []
    if (atmStrike == null) return fno.rows.slice(0, 12)
    const idx = fno.rows.findIndex((r) => String(r.strike) === String(atmStrike))
    if (idx < 0) return fno.rows.slice(0, 12)
    const from = Math.max(0, idx - 5)
    return fno.rows.slice(from, from + 11)
  }, [fno, atmStrike])

  const backtestInterp = useMemo(
    () => interpretationBullets(backtest?.interpretation, displaySym, backtest?.metrics),
    [backtest?.interpretation, backtest?.metrics, displaySym],
  )

  return (
    <section className="panel research-desk wireframe-research symbol-workspace">
      <header className="research-topbar">
        <div className="research-brand">
          <p className="eyebrow">TradePilot</p>
          <h1>Symbol Workspace</h1>
        </div>
        <div className="research-search-wrap" ref={searchWrapRef}>
          <label className="research-search">
            <span className="visually-hidden">Search symbol</span>
            <span className="research-ico research-ico-search" aria-hidden="true" />
            <input
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value.toUpperCase())
                setSuggestOpen(true)
              }}
              onFocus={() => {
                if (suggestions.length > 0) setSuggestOpen(true)
              }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  if (!suggestions.length) return
                  setSuggestOpen(true)
                  setActiveSuggest((i) => (i + 1) % suggestions.length)
                  return
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  if (!suggestions.length) return
                  setSuggestOpen(true)
                  setActiveSuggest((i) => (i <= 0 ? suggestions.length - 1 : i - 1))
                  return
                }
                if (e.key === 'Escape') {
                  setSuggestOpen(false)
                  setActiveSuggest(-1)
                  return
                }
                if (e.key === 'Enter') {
                  e.preventDefault()
                  if (suggestOpen && activeSuggest >= 0 && suggestions[activeSuggest]) {
                    pickSuggestion(suggestions[activeSuggest].symbol)
                    return
                  }
                  void load()
                }
              }}
              placeholder="Search symbol"
              aria-label="Search NSE symbol"
              aria-autocomplete="list"
              aria-expanded={suggestOpen}
              aria-controls="symbol-suggest-list"
              role="combobox"
              autoComplete="off"
            />
            {symbol ? (
              <button
                type="button"
                className="ghost-btn research-search-clear"
                aria-label="Clear symbol"
                onClick={() => {
                  setSymbol('')
                  setLoadedSymbol('')
                  setSuggestions([])
                  setSuggestOpen(false)
                  setOverview(null)
                  setTechnical(null)
                  setNews(null)
                  setFno(null)
                  setSimilar([])
                  setSimilarMeta(null)
                  setCompareSelected([])
                  setCandles([])
                  setInsight(null)
                  setEvalResult(null)
                  setBacktest(null)
                }}
              >
                ×
              </button>
            ) : null}
            <button type="button" className="primary-button" onClick={() => void load()} disabled={loading || !symbol.trim()}>
              {loading ? 'Loading…' : 'Load'}
            </button>
          </label>
          {suggestOpen && (suggestions.length > 0 || suggestLoading) ? (
            <ul id="symbol-suggest-list" className="research-suggest-list" role="listbox">
              {suggestLoading && suggestions.length === 0 ? (
                <li className="research-suggest-empty">Searching…</li>
              ) : null}
              {suggestions.map((row, index) => (
                <li key={row.symbol} role="option" aria-selected={index === activeSuggest}>
                  <button
                    type="button"
                    className={`research-suggest-item ${index === activeSuggest ? 'is-active' : ''}`}
                    onMouseEnter={() => setActiveSuggest(index)}
                    onClick={() => pickSuggestion(row.symbol)}
                  >
                    <strong>{row.symbol}</strong>
                    <span>{row.asset_class === 'ETF' ? 'ETF' : 'Stock'}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <span className="research-mode-tag">
          <span className="research-ico research-ico-help" aria-hidden="true" />
          FA and TA
        </span>
      </header>

      <div className="research-tabs" role="tablist" aria-label="Symbol workspace tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={tab === item.id ? 'research-tab active' : 'research-tab'}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <div className="status error">{error}</div> : null}

      {tab === 'overview' ? (
        <div className="research-overview-grid">
          <div className="research-chart-card research-area-chart">
            <div className="research-chart-head">
              <div>
                <h2>{displaySym}</h2>
                <p className="research-live-line">
                  <span className="research-live-tag">Live</span>
                  {overview?.current_price != null ? (
                    <LiveValue
                      value={overview.current_price}
                      formatted={formatPrice(overview.current_price)}
                      className="research-live-price"
                    />
                  ) : (
                    <span className="research-live-price">{formatPrice(overview?.last_close)}</span>
                  )}
                  {overview?.current_price_change_percent != null ? (
                    <ChangeChip
                      value={overview.current_price_change_percent}
                      formatPercent={formatPercent}
                      valueClass={valueClass}
                    />
                  ) : null}
                </p>
              </div>
            </div>
            <SetupChart candles={candles} levels={chartLevels} height={360} variant="inspect" />
            {candles.length > 0 && !evalResult?.has_setup ? (
              <p className="field-hint research-chart-hint">
                No confirmed Entry / Stop / Target on the latest bar — run Evaluate after Load.
              </p>
            ) : null}
          </div>

          <aside className="research-side-card research-area-fa">
            <h3>
              <span className="research-ico research-ico-bars" aria-hidden="true" />
              FA Snapshot
            </h3>
            <dl className="research-dl">
              <div>
                <dt>Last / live</dt>
                <dd className="research-dd-stack">
                  <span className="research-metric-value">
                    {formatPrice(overview?.current_price ?? overview?.last_close)}
                  </span>
                  {overview?.current_price_change_percent != null ? (
                    <ChangeChip
                      value={overview.current_price_change_percent}
                      formatPercent={formatPercent}
                      valueClass={valueClass}
                    />
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>52W range</dt>
                <dd className="research-metric-value">
                  {formatPrice(overview?.low_52w)} – {formatPrice(overview?.high_52w)}
                </dd>
              </div>
              <div>
                <dt>Sector</dt>
                <dd className="research-sector-value">{overview?.sector || '—'}</dd>
              </div>
              <div>
                <dt>Caution flags</dt>
                <dd className="research-flags">
                  {flags.length ? (
                    flags.map((flag) => (
                      <span key={flag} className="research-flag-pill">
                        <span className="research-ico research-ico-flag" aria-hidden="true" />
                        {flag}
                      </span>
                    ))
                  ) : (
                    <span className="research-flag-none">
                      <span className="research-ico research-ico-flag" aria-hidden="true" />
                      None
                    </span>
                  )}
                </dd>
              </div>
            </dl>
          </aside>

          <div className="research-actions research-area-actions">
            <button
              type="button"
              className="primary-button research-action-btn"
              onClick={() => void runEvaluate()}
              disabled={evalLoading || !symbol.trim()}
            >
              <span className="research-ico research-ico-search" aria-hidden="true" />
              {evalLoading ? 'Evaluating…' : 'Evaluate'}
            </button>
            <button
              type="button"
              className="secondary-button research-action-btn"
              onClick={() => void runBacktest()}
              disabled={backtestLoading || !symbol.trim()}
            >
              <span className="research-ico research-ico-bars" aria-hidden="true" />
              {backtestLoading ? 'Backtesting…' : 'Backtest'}
            </button>
          </div>

          <aside className="research-side-card research-area-fit">
            <h3>
              <span className="research-ico research-ico-trend" aria-hidden="true" />
              Technical setup fit
            </h3>
            <div className="research-fit-row">
              <FitStatusMark tone={fit.tone} />
              <div>
                <p className="research-fit-title">{fit.title}</p>
                <p className="research-fit-level">
                  Fit: <strong>{fit.fit}</strong>
                </p>
              </div>
            </div>
            <ul className="research-fit-criteria">
              {fit.criteria.map((item) => (
                <li key={item}>
                  <span className="research-list-mark" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="research-fit-badges">
              <span className={`research-status-pill ${fit.ok ? 'is-armed' : 'is-muted'}`}>
                Swing: {fit.ok ? 'Eligible now' : 'No confirmed setup'}
              </span>
              <span className="research-status-pill is-muted">Intraday: open morning board</span>
            </div>
          </aside>

          <section className="research-insight-card research-area-insight ai-prose" aria-label="AI insight">
            <h3>
              <span className="research-ico research-ico-spark" aria-hidden="true" />
              AI Insight (Grounded Only)
            </h3>
            {insight ? (
              <>
                {insight.headline ? <p className="detail-lede">{insight.headline}</p> : null}
                <ul className="research-prose-list">
                  {insight.bullets.map((bullet) => (
                    <li key={bullet}>
                      <span className="research-list-mark is-spark" aria-hidden="true" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
                <p className="field-hint">
                  {insight.provider === 'gemini' || insight.provider === 'llm'
                    ? 'Grounded LLM polish — does not invent Entry / Stop / Target.'
                    : 'Template insight from candle/research facts only.'}
                </p>
              </>
            ) : (
              <p className="field-hint">Load a symbol to generate a grounded insight.</p>
            )}
          </section>

          {backtest ? (
            <div className="research-backtest-card research-area-backtest ai-prose">
              <h3>Backtest summary</h3>
              <div className="metric-row">
                <div className="metric-tile">
                  <span>Win rate</span>
                  <strong>{formatPercent(backtest.metrics.win_rate)}</strong>
                </div>
                <div className="metric-tile">
                  <span>Trade count</span>
                  <strong>{backtest.metrics.total_trades}</strong>
                </div>
                <div className="metric-tile">
                  <span>Avg R</span>
                  <strong className={valueClass(backtest.metrics.average_r)}>
                    {formatNumber(backtest.metrics.average_r, 2)}
                  </strong>
                </div>
                <div className="metric-tile">
                  <span>Max DD</span>
                  <strong>{formatPercent(backtest.metrics.maximum_drawdown)}</strong>
                </div>
              </div>
              {backtest.interpretation ? (
                <p className="research-interpretation">
                  {backtest.interpretation_provider === 'llm' ||
                  backtest.interpretation_provider === 'gemini' ? (
                    <span className="ai-polished-badge">AI-polished</span>
                  ) : null}{' '}
                  {backtest.interpretation}
                </p>
              ) : null}
              <p className="field-hint">Open the Evaluate tab for the full chart + interpreter layout.</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'technical' && (
        <div className="research-technical-layout">
          {!technical && !loading ? (
            <p className="field-hint">Load a symbol to see technicals.</p>
          ) : (
            <>
              <div className="research-chart-card research-tech-chart">
                <div className="research-chart-head">
                  <h2>Price Chart</h2>
                  <p className="field-hint">{displaySym} · daily structure</p>
                </div>
                <SetupChart candles={candles} levels={structureLevels} height={360} variant="structure" />
                <ul className="research-chart-legend" aria-label="Chart level legend">
                  <li>
                    <span className="research-legend-swatch is-support" /> Support
                  </li>
                  <li>
                    <span className="research-legend-swatch is-resistance" /> Resistance
                  </li>
                  <li>
                    <span className="research-legend-swatch is-trend" /> Trendline (EMA 20)
                  </li>
                </ul>
              </div>

              <div className="research-tech-side">
                <aside className="research-side-card research-tech-panel">
                  <h3>
                    <span className="research-ico research-ico-trend" aria-hidden="true" />
                    Technical Panel
                  </h3>
                  <dl className="research-dl">
                    <div>
                      <dt>S/R levels</dt>
                      <dd className="research-metric-value">
                        {formatPrice(structureLevels.resistance)} / {formatPrice(structureLevels.support)}
                      </dd>
                    </div>
                    <div>
                      <dt>ATR</dt>
                      <dd className="research-metric-value">{formatNumber(atrValue, 2)}</dd>
                    </div>
                    <div>
                      <dt>Swing fit</dt>
                      <dd className="research-dd-stack">
                        <span
                          className={`research-fit-badge is-${String(swingFitLabel).toLowerCase()}`}
                        >
                          <SwingFitIcon level={String(swingFitLabel)} />
                          <span>{swingFitLabel}</span>
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>Eligible</dt>
                      <dd>
                        <span className={`research-status-pill ${swingEligible ? 'is-armed' : 'is-muted'}`}>
                          {swingEligible ? 'Yes' : 'No'}
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>ORB snapshot</dt>
                      <dd className="research-metric-value">
                        {technical?.orb_snapshot != null
                          ? formatPrice(technical.orb_snapshot)
                          : technical?.orb_status === 'no_1m_data'
                            ? 'No 1m data'
                            : technical?.orb_status === 'building'
                              ? 'Building…'
                              : '—'}
                      </dd>
                    </div>
                    <div>
                      <dt>Armed</dt>
                      <dd>
                        <span
                          className={`research-status-pill ${technical?.orb_armed ? 'is-armed' : 'is-muted'}`}
                        >
                          {technical?.orb_armed ? 'True' : 'False'}
                        </span>
                      </dd>
                    </div>
                  </dl>
                  {(technical?.orb_high != null || technical?.orb_low != null) && (
                    <p className="field-hint research-orb-hint">
                      OR high {formatPrice(technical.orb_high)} · OR low {formatPrice(technical.orb_low)}
                    </p>
                  )}
                  <ul className="research-fit-criteria research-tech-signals">
                    {(technical?.indicators || []).slice(0, 5).map((row) => (
                      <li key={row.name}>
                        <span className="research-list-mark" aria-hidden="true" />
                        <span>
                          <strong>{row.name}</strong> · {row.signal}
                          {row.value != null ? ` · ${formatNumber(row.value, 2)}` : ''}
                        </span>
                      </li>
                    ))}
                  </ul>
                </aside>

                <aside className="research-side-card research-tech-note" aria-label="Technical disclaimer">
                  <p className="research-disclaimer">
                    Structure levels are pivots + EMA context. Entry / Stop / Target come only from Evaluate
                    (engine) — this panel never invents trade prices.
                  </p>
                  {evalResult?.has_setup && evalResult.candidate ? (
                    <p className="field-hint research-plan-strip">
                      Confirmed plan: {directionLabel(evalResult.candidate.direction)} · Entry{' '}
                      {formatPrice(evalResult.candidate.entry_price)} · Stop{' '}
                      {formatPrice(evalResult.candidate.stop_loss)} · Target{' '}
                      {formatPrice(evalResult.candidate.target)}
                    </p>
                  ) : null}
                  {backtest ? (
                    <p className="field-hint">
                      Last backtest · {backtest.metrics.total_trades} trades · win{' '}
                      {formatPercent(backtest.metrics.win_rate)} · P/L{' '}
                      <span className={valueClass(backtest.metrics.total_pnl)}>
                        {formatPrice(backtest.metrics.total_pnl)}
                      </span>
                    </p>
                  ) : null}
                </aside>
              </div>

              <div className="research-actions research-tech-actions">
                <button
                  type="button"
                  className="primary-button research-action-btn"
                  onClick={() => void runEvaluate()}
                  disabled={evalLoading || !symbol.trim()}
                >
                  <span className="research-ico research-ico-search" aria-hidden="true" />
                  {evalLoading ? 'Evaluating…' : 'Evaluate'}
                </button>
                <button
                  type="button"
                  className="secondary-button research-action-btn"
                  onClick={() => void runBacktest()}
                  disabled={backtestLoading || !symbol.trim()}
                >
                  <span className="research-ico research-ico-bars" aria-hidden="true" />
                  {backtestLoading ? 'Backtesting…' : 'Backtest'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'fundamentals' && (
        <div className="research-fundamentals-layout">
          {!overview && !loading ? (
            <p className="field-hint">Load a symbol to see fundamentals snapshot.</p>
          ) : (
            <>
              <aside className="research-side-card research-fa-snapshot">
                <h3>
                  <span className="research-ico research-ico-building" aria-hidden="true" />
                  Business snapshot
                </h3>
                <p className="research-fa-sector-label">Sector</p>
                <p className="research-fa-sector-value">{overview?.sector || 'Unclassified'}</p>

                <div className="research-fa-quality">
                  <p className="research-fa-quality-label">Quality checks</p>
                  <p className="field-hint research-fa-quality-hint">
                    Three fixed eligibility checks — clear means no issue on that check.
                  </p>
                  <ul className="research-fa-check-list" aria-label="Quality checks">
                    {(overview?.quality_checks || []).map((check) => (
                      <li
                        key={check.id}
                        className={`research-fa-check is-${check.status === 'warn' ? 'warn' : 'clear'}`}
                      >
                        <span className="research-fa-check-mark" aria-hidden="true">
                          {check.status === 'warn' ? '!' : '✓'}
                        </span>
                        <div className="research-fa-check-copy">
                          <strong>{check.label}</strong>
                          <span>{check.detail}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>

                <p className={`research-fa-caution ${flags.length ? 'is-warn' : 'is-ok'}`}>
                  <span className="research-ico research-ico-flag" aria-hidden="true" />
                  {overview?.caution_summary ||
                    (flags.length ? `Caution: ${flags[0]}` : 'No near-term caution')}
                </p>

                <div className="research-fa-meta">
                  <div className="research-fa-meta-tile">
                    <span className="research-fa-meta-label">52W range</span>
                    <strong className="research-fa-meta-value">
                      {formatPrice(overview?.low_52w)} - {formatPrice(overview?.high_52w)}
                    </strong>
                  </div>
                  <div className="research-fa-meta-tile">
                    <span className="research-fa-meta-label">52W position</span>
                    <strong className="research-fa-meta-value">
                      {overview?.range_52w_position_pct != null
                        ? `${formatNumber(overview.range_52w_position_pct, 1)}%`
                        : '—'}
                    </strong>
                  </div>
                  <div className="research-fa-meta-tile">
                    <span className="research-fa-meta-label">History</span>
                    <strong className="research-fa-meta-value">{overview?.candle_count ?? 0} bars</strong>
                  </div>
                </div>
              </aside>

              <aside className="research-side-card research-fa-metrics">
                <h3>
                  <span className="research-ico research-ico-bars" aria-hidden="true" />
                  Metrics table
                </h3>
                <div className="research-fa-table-wrap">
                  <table className="research-fa-table">
                    <thead>
                      <tr>
                        <th scope="col">Metric</th>
                        <th scope="col" className="num">
                          Value
                        </th>
                        <th scope="col">Note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(overview?.fa_proxies || []).map((row) => (
                        <tr key={row.label} className={row.available === false ? 'is-unavailable' : undefined}>
                          <td>{row.label}</td>
                          <td className="num">
                            {row.change_percent != null ? (
                              <span className={valueClass(row.change_percent)}>
                                {Number(row.change_percent) > 0 ? '+' : ''}
                                {formatPercent(row.change_percent)}
                              </span>
                            ) : row.available === false ? (
                              <span className="research-fa-dash">—</span>
                            ) : (
                              row.value || '—'
                            )}
                          </td>
                          <td>{row.note || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="field-hint research-fa-note">
                  Note: Not a full DCF. Revenue / Margin / ROE use reported fiscal figures when available;
                  other rows are price/liquidity proxies for filters.
                </p>
              </aside>

              <div className="research-actions research-fa-actions">
                <button
                  type="button"
                  className="primary-button research-action-btn"
                  onClick={() => void runEvaluate()}
                  disabled={evalLoading || !symbol.trim()}
                >
                  <span className="research-ico research-ico-search" aria-hidden="true" />
                  {evalLoading ? 'Evaluating…' : 'Evaluate'}
                </button>
                <button
                  type="button"
                  className="secondary-button research-action-btn"
                  onClick={() => void runBacktest()}
                  disabled={backtestLoading || !symbol.trim()}
                >
                  <span className="research-ico research-ico-bars" aria-hidden="true" />
                  {backtestLoading ? 'Backtesting…' : 'Backtest'}
                </button>
              </div>

              <aside className="research-side-card research-fa-disclaimer" aria-label="Fundamentals disclaimer">
                <p className="research-disclaimer">
                  Fundamentals here are a sellable snapshot for filters and caution — not valuation advice.
                  Entry / Stop / Target still come only from Evaluate (engine).
                </p>
                {evalResult?.has_setup && evalResult.candidate ? (
                  <p className="field-hint research-plan-strip">
                    Confirmed plan: {directionLabel(evalResult.candidate.direction)} · Entry{' '}
                    {formatPrice(evalResult.candidate.entry_price)} · Stop{' '}
                    {formatPrice(evalResult.candidate.stop_loss)} · Target{' '}
                    {formatPrice(evalResult.candidate.target)}
                  </p>
                ) : null}
                {backtest ? (
                  <p className="field-hint">
                    Last backtest · {backtest.metrics.total_trades} trades · win{' '}
                    {formatPercent(backtest.metrics.win_rate)} · P/L{' '}
                    <span className={valueClass(backtest.metrics.total_pnl)}>
                      {formatPrice(backtest.metrics.total_pnl)}
                    </span>
                  </p>
                ) : null}
              </aside>
            </>
          )}
        </div>
      )}

      {tab === 'news' && (
        <div className="research-news-layout">
          <aside className="research-side-card research-news-list-card">
            <h3>
              <span className="research-ico research-ico-news" aria-hidden="true" />
              News List
            </h3>
            {newsCards.length === 0 ? (
              <p className="field-hint">{news?.detail || 'No announcements or events loaded for this symbol.'}</p>
            ) : (
              <ul className="research-news-cards">
                {newsCards.map((item) => (
                  <li key={`${item.kind}-${item.title}-${item.published_at}`}>
                    <article className="research-news-card">
                      <strong>{item.title}</strong>
                      <span className="research-news-card-meta">
                        {item.kind === 'event' ? item.category || 'Event' : item.source || 'NSE'}
                        {item.published_at ? ` · ${formatNewsWhen(item.published_at, formatDateTime)}` : ''}
                      </span>
                      {isHttpUrl(item.url) ? (
                        <a href={item.url!} target="_blank" rel="noreferrer" className="research-news-link">
                          Open filing
                        </a>
                      ) : null}
                    </article>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          <aside className="research-side-card research-ca-panel">
            <div className="research-ca-head">
              <h3>
                <span className="research-ico research-ico-calendar" aria-hidden="true" />
                Corporate Actions Calendar
              </h3>
              <div className="research-ca-nav">
                <button
                  type="button"
                  className="ghost-btn"
                  aria-label="Previous month"
                  onClick={() =>
                    setCaMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))
                  }
                >
                  ‹
                </button>
                <span>
                  {caMonth.toLocaleString('en-IN', { month: 'long', year: 'numeric' })}
                </span>
                <button
                  type="button"
                  className="ghost-btn"
                  aria-label="Next month"
                  onClick={() =>
                    setCaMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))
                  }
                >
                  ›
                </button>
              </div>
            </div>

            <div className="research-ca-main">
              <div className="research-ca-grid-wrap">
                <div className="research-ca-weekday" aria-hidden="true">
                  {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
                    <span key={day}>{day}</span>
                  ))}
                </div>
                <div className="research-ca-grid" role="grid" aria-label="Corporate actions month">
                  {caCells.map((cell, index) => {
                    if (!cell) {
                      return <div key={`empty-${index}`} className="research-ca-cell is-empty" />
                    }
                    const dayActions = actionsForDay(corporateActions, cell.date)
                    const isBlock = dayActions.some((action) => (action.block_sessions || 1) > 1)
                    return (
                      <div
                        key={cell.date.toISOString()}
                        className={`research-ca-cell ${dayActions.length ? 'has-event' : ''} ${isBlock ? 'is-block' : ''}`}
                      >
                        <span className="research-ca-day">{cell.day}</span>
                        {dayActions.slice(0, 2).map((action) => (
                          <span
                            key={`${action.ex_date}-${action.type}`}
                            className={`research-ca-chip is-${action.type.toLowerCase()}`}
                            title={`${caChipLabel(action)} · ex ${action.ex_date}`}
                          >
                            {caChipLabel(action)}
                          </span>
                        ))}
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="research-ca-rail">
                <div
                  className={`research-ca-warning ${news?.trading_caution ? 'is-warn' : 'is-ok'}`}
                  role="status"
                >
                  {news?.trading_caution
                    ? `Warning: ${(news.caution_summary || 'Avoid trading through dangerous events').replace(
                        /^(Caution|Warning):\s*/i,
                        '',
                      )}`
                    : 'No near-term trading caution for this symbol'}
                </div>
                <div className="research-ca-actions">
                  <button
                    type="button"
                    className="ghost-btn research-ca-link"
                    onClick={() => onOpenEligibility?.()}
                  >
                    Eligibility
                  </button>
                  <button
                    type="button"
                    className="secondary-button research-action-btn"
                    onClick={() => onOpenFilters?.()}
                  >
                    Filters
                  </button>
                </div>
              </div>
            </div>

            <ul className="research-ca-upcoming">
              {(monthActions.length ? monthActions : corporateActions.slice(-5)).map((action) => (
                <li key={`${action.ex_date}-${action.type}-${action.source}`}>
                  <strong>{caChipLabel(action)}</strong>
                  <span>
                    Ex {formatCaDate(action.ex_date)}
                    {action.block_sessions && action.block_sessions > 1
                      ? ` · ${action.block_sessions}-session block`
                      : ''}
                    {action.source ? ` · ${action.source}` : ''}
                  </span>
                </li>
              ))}
              {!corporateActions.length ? (
                <li className="field-hint">No corporate actions on file for this symbol.</li>
              ) : null}
            </ul>
          </aside>

          <aside className="research-side-card research-news-disclaimer" aria-label="News disclaimer">
            <p className="research-disclaimer">
              Disclaimer: News and CA dates are for event awareness and eligibility filters — not trade
              advice. Entry / Stop / Target still come only from Evaluate (engine).
            </p>
          </aside>
        </div>
      )}

      {tab === 'fno' && (
        <div className="research-fno-layout">
          <aside className="research-side-card research-fno-context">
            <div className="research-fno-context-head">
              <h3>
                <span className="research-ico research-ico-fno" aria-hidden="true" />
                F&O Context
              </h3>
              <label className="research-fno-expiry">
                <span className="visually-hidden">Expiry</span>
                <select
                  value={fnoExpiry}
                  onChange={(e) => setFnoExpiry(e.target.value)}
                  aria-label="Option expiry"
                >
                  <option value="current_week">Current week</option>
                  <option value="next_week">Next week</option>
                  <option value="current_month">Current month</option>
                  <option value="next_month">Next month</option>
                </select>
              </label>
            </div>

            {!fno || fno.status !== 'ok' || !fnoRows.length ? (
              <div className="research-fno-unavailable" role="status">
                <strong>Unavailable</strong>
                <span>
                  {fno?.detail ||
                    'When F&O data unavailable show Unavailable. Live option chain needs Upstox.'}
                </span>
              </div>
            ) : (
              <>
                <div className="research-fno-meta">
                  <span>
                    Spot <strong>{formatPrice(fno.spot)}</strong>
                  </span>
                  <span>
                    Expiry <strong>{fno.expiry || fno.expiry_date || '—'}</strong>
                  </span>
                  <span>
                    Near ATM <strong>{formatNumber(atmStrike, 0)}</strong>
                  </span>
                </div>
                <div className="fno-chain research-fno-chain">
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
                          <th className="col-strike">Strike</th>
                          <th className="col-put">OI</th>
                          <th className="col-put">LTP</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fnoRows.map((row) => {
                          const isAtm = atmStrike != null && String(row.strike) === String(atmStrike)
                          const isCallWall =
                            fno.call_wall_strike != null &&
                            String(row.strike) === String(fno.call_wall_strike)
                          const isPutWall =
                            fno.put_wall_strike != null &&
                            String(row.strike) === String(fno.put_wall_strike)
                          return (
                            <tr
                              key={String(row.strike)}
                              className={[
                                isAtm ? 'is-atm' : '',
                                isCallWall || isPutWall ? 'is-wall' : '',
                              ]
                                .filter(Boolean)
                                .join(' ')}
                            >
                              <td className="col-call num-cell">{formatPrice(row.call_ltp)}</td>
                              <td className="col-call num-cell">{formatNumber(row.call_oi, 0)}</td>
                              <td className="col-strike">
                                <span className="strike-value">{formatNumber(row.strike, 0)}</span>
                                {isAtm ? <em className="atm-pill">ATM</em> : null}
                                {isCallWall ? <em className="wall-pill is-call">CW</em> : null}
                                {isPutWall ? <em className="wall-pill is-put">PW</em> : null}
                              </td>
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
          </aside>

          <aside className="research-side-card research-fno-metrics">
            <ul className="research-fno-metric-list">
              <li className="research-fno-metric">
                <span className="research-ico research-ico-trend" aria-hidden="true" />
                <div>
                  <span className="research-fno-metric-label">Futures premium</span>
                  <strong>
                    {fno?.futures_premium_status === 'ok' && fno.futures_premium != null
                      ? formatPrice(fno.futures_premium)
                      : 'Unavailable'}
                  </strong>
                </div>
              </li>
              <li className="research-fno-metric">
                <span className="research-ico research-ico-bars" aria-hidden="true" />
                <div>
                  <span className="research-fno-metric-label">OI change</span>
                  <strong
                    className={
                      fno?.oi_change_status === 'ok' && fno.oi_change != null
                        ? valueClass(fno.oi_change)
                        : undefined
                    }
                  >
                    {fno?.oi_change_status === 'ok' && fno.oi_change != null
                      ? `${Number(fno.oi_change) > 0 ? '+' : ''}${formatNumber(fno.oi_change, 0)}`
                      : 'Unavailable'}
                  </strong>
                  {fno?.oi_change_status === 'ok' ? (
                    <span className="research-fno-metric-sub">
                      Call {formatNumber(fno.call_oi_change, 0)} · Put{' '}
                      {formatNumber(fno.put_oi_change, 0)}
                    </span>
                  ) : null}
                </div>
              </li>
              <li className="research-fno-metric">
                <span className="research-ico research-ico-pcr" aria-hidden="true" />
                <div>
                  <span className="research-fno-metric-label">PCR</span>
                  <strong>
                    {fno?.status === 'ok' && fno.pcr != null ? formatNumber(fno.pcr, 2) : 'Unavailable'}
                  </strong>
                </div>
              </li>
              <li className="research-fno-metric">
                <span className="research-ico research-ico-walls" aria-hidden="true" />
                <div>
                  <span className="research-fno-metric-label">Options wall levels</span>
                  <strong>
                    {fno?.status === 'ok' && (fno.call_wall_strike != null || fno.put_wall_strike != null)
                      ? `C ${formatNumber(fno.call_wall_strike, 0)} · P ${formatNumber(fno.put_wall_strike, 0)}`
                      : 'Unavailable'}
                  </strong>
                  {fno?.status === 'ok' && fno.call_wall_oi != null ? (
                    <span className="research-fno-metric-sub">
                      Call OI {formatNumber(fno.call_wall_oi, 0)} · Put OI{' '}
                      {formatNumber(fno.put_wall_oi, 0)}
                    </span>
                  ) : null}
                </div>
              </li>
            </ul>
            <p className="research-fno-caution">Caution: Not advice.</p>
          </aside>

          <aside className="research-side-card research-fno-disclaimer" aria-label="F&O disclaimer">
            <p className="research-disclaimer">
              Disclaimer: All F&O data is for educational purposes only and should not be considered
              financial advice. Entry / Stop / Target still come only from Evaluate (engine).
            </p>
          </aside>
        </div>
      )}

      {tab === 'similar' && (
        <div className="research-similar-layout">
          <div className="research-similar-head">
            <h3>
              <span className="research-ico research-ico-similar" aria-hidden="true" />
              Similar setups
            </h3>
            {similarMeta?.direction || similarMeta?.setup_family ? (
              <p className="research-similar-sub">
                {similarMeta.direction ? directionLabel(similarMeta.direction) : null}
                {similarMeta.direction && similarMeta.setup_family ? ' · ' : null}
                {similarMeta.setup_family ? formatSetupFamily(similarMeta.setup_family) : null}
                {similarMeta.query_source ? ` · via ${similarMeta.query_source}` : null}
              </p>
            ) : null}
          </div>

          {similar.length === 0 ? (
            <div className="research-similar-empty" role="status">
              <strong>No similar peers yet</strong>
              <span>
                {similarMeta?.detail ||
                  'No similar historical setups found. Run Find Setups or Evaluate to build grounded peers.'}
              </span>
            </div>
          ) : (
            <ul className="research-similar-grid">
              {similar.map((item) => {
                const selected = compareSelected.includes(item.symbol)
                const family = formatSetupFamily(item.setup_name || similarMeta?.setup_family)
                return (
                  <li key={`${item.symbol}-${item.confirmation_time}-${item.distance}`}>
                    <article
                      className={`research-similar-card ${selected ? 'is-selected' : ''}`}
                      onClick={() => {
                        setCompareSelected((prev) =>
                          prev.includes(item.symbol)
                            ? prev.filter((s) => s !== item.symbol)
                            : [...prev, item.symbol],
                        )
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setCompareSelected((prev) =>
                            prev.includes(item.symbol)
                              ? prev.filter((s) => s !== item.symbol)
                              : [...prev, item.symbol],
                          )
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      aria-pressed={selected}
                    >
                      <header className="research-similar-card-head">
                        <button
                          type="button"
                          className="research-similar-symbol"
                          onClick={(e) => {
                            e.stopPropagation()
                            void load(item.symbol)
                          }}
                        >
                          {item.symbol}
                        </button>
                        <span className={`research-similar-check ${selected ? 'is-on' : ''}`} aria-hidden="true" />
                      </header>
                      <dl className="research-similar-dl">
                        <div>
                          <dt>Direction Score</dt>
                          <dd>
                            {item.quality_score != null && String(item.quality_score) !== ''
                              ? formatNumber(item.quality_score, 1)
                              : '—'}
                          </dd>
                        </div>
                        <div>
                          <dt>Entry</dt>
                          <dd>{item.entry_price != null ? formatPrice(item.entry_price) : '—'}</dd>
                        </div>
                        <div>
                          <dt>Stop</dt>
                          <dd>{item.stop_loss != null ? formatPrice(item.stop_loss) : '—'}</dd>
                        </div>
                        <div>
                          <dt>Shared setup family</dt>
                          <dd>{family}</dd>
                        </div>
                      </dl>
                      {item.blurb || item.forward_return_pct != null ? (
                        <p className="research-similar-blurb">
                          {item.blurb ||
                            (item.forward_return_pct != null
                              ? `Next ${item.forward_bars ?? 10} sessions averaged ${item.forward_return_pct}% (candle path, not live P&L).`
                              : null)}
                        </p>
                      ) : null}
                    </article>
                  </li>
                )
              })}
            </ul>
          )}

          <div className="research-similar-actions">
            <button
              type="button"
              className="secondary-button research-similar-compare"
              disabled={similar.length === 0}
              onClick={() => {
                const picks = compareSelected.length
                  ? compareSelected
                  : similar.slice(0, 2).map((s) => s.symbol)
                if (picks.length < 1) return
                setCompareLeft(picks[0])
                setCompareRight(picks[1] || picks[0])
                setTab('compare')
              }}
            >
              <span className="research-similar-check is-on" aria-hidden="true" />
              Compare
            </button>
            {compareSelected.length > 0 ? (
              <p className="field-hint">
                Selected {compareSelected.join(' · ')}. Compare opens side-by-side grounded fields.
              </p>
            ) : null}
          </div>

          <aside className="research-side-card research-similar-note" aria-label="Similar setups note">
            <p className="research-disclaimer">
              Note: Grounded fields only — no fabricated peer metrics. Entry / Stop come from engine
              scan or Evaluate evidence.
            </p>
          </aside>
        </div>
      )}

      {tab === 'compare' && (
        <CompareNamesDesk
          baseUrl={baseUrl}
          leftSymbol={compareLeft}
          rightSymbol={compareRight}
          formatPrice={formatPrice}
          embedded
          onOpenResearch={(sym) => {
            setSymbol(sym)
            setTab('overview')
            void load(sym)
          }}
        />
      )}

      {tab === 'evaluate' && (
        <div className="research-evaluate-layout">
          <header className="research-evaluate-title">
            <h2>
              <span className="research-ico research-ico-evaluate" aria-hidden="true" />
              Evaluate · {displaySym}
            </h2>
            <p className="research-evaluate-lede">
              Engine owns Entry / Stop / Target. Interpreter summarizes metrics only — never invents
              trades.
            </p>
          </header>

          <div className="research-side-card research-evaluate-controls">
            <label className="research-evaluate-field">
              <span>Strategy</span>
              <select value={evalStrategy} disabled aria-label="Strategy">
                <option value="BreakoutRetest">BreakoutRetest</option>
              </select>
            </label>
            <div className="research-evaluate-range" role="group" aria-label="Date range">
              <label className="research-evaluate-field">
                <span>Date range</span>
                <input
                  type="date"
                  value={evalStartDate}
                  max={evalEndDate}
                  onChange={(e) => setEvalStartDate(e.target.value)}
                />
              </label>
              <span className="research-evaluate-range-sep" aria-hidden="true">
                →
              </span>
              <label className="research-evaluate-field research-evaluate-field-end">
                <span className="visually-hidden">End date</span>
                <input
                  type="date"
                  value={evalEndDate}
                  min={evalStartDate}
                  onChange={(e) => setEvalEndDate(e.target.value)}
                />
              </label>
            </div>
            <div className="research-evaluate-actions">
              <button
                type="button"
                className="secondary-button research-action-btn"
                onClick={() => void runEvaluate()}
                disabled={evalLoading || !symbol.trim()}
              >
                {evalLoading ? 'Running…' : 'Run evaluate'}
              </button>
              <button
                type="button"
                className="primary-button research-action-btn"
                onClick={() => void runBacktest()}
                disabled={backtestLoading || !symbol.trim()}
              >
                {backtestLoading ? 'Running…' : 'Run backtest'}
              </button>
            </div>
            {actionStatus ? (
              <p className="research-evaluate-status" role="status">
                {actionStatus}
              </p>
            ) : null}
          </div>

          <aside className="research-side-card research-evaluate-chart">
            <div className="research-chart-head">
              <h3>
                <span className="research-ico research-ico-bars" aria-hidden="true" />
                Price Chart
              </h3>
              {evalResult?.has_setup && evalResult.candidate ? (
                <p className="research-evaluate-plan">
                  {directionLabel(evalResult.candidate.direction)} · Entry{' '}
                  {formatPrice(evalResult.candidate.entry_price)} · SL{' '}
                  {formatPrice(evalResult.candidate.stop_loss)} · Target{' '}
                  {formatPrice(evalResult.candidate.target)}
                </p>
              ) : evalResult ? (
                <p className="field-hint research-evaluate-nosetup" role="status">
                  Evaluate finished: {evalResult.status}
                  {evalResult.reason ? ` — ${evalResult.reason}` : ''}. No Entry / SL / Target on the
                  latest bar.
                </p>
              ) : (
                <p className="field-hint">Entry / SL / Target appear after a confirmed Evaluate.</p>
              )}
            </div>
            {candles.length ? (
              <SetupChart candles={candles} levels={chartLevels} height={340} variant="inspect" />
            ) : (
              <div className="research-evaluate-chart-empty" role="status">
                Load a symbol or Run evaluate to draw the price chart.
              </div>
            )}
          </aside>

          <aside className="research-side-card research-evaluate-results">
            <h3>
              <span className="research-ico research-ico-spark" aria-hidden="true" />
              Results
            </h3>
            <ul className="research-evaluate-metrics">
              {[
                {
                  id: 'win',
                  label: 'Win rate',
                  value: backtest ? formatPercent(backtest.metrics.win_rate) : '—',
                  ready: Boolean(backtest),
                  tone: undefined as string | undefined,
                },
                {
                  id: 'trades',
                  label: 'Trade count',
                  value: backtest ? String(backtest.metrics.total_trades) : '—',
                  ready: Boolean(backtest),
                  tone: undefined as string | undefined,
                },
                {
                  id: 'avgr',
                  label: 'Avg R',
                  value: backtest ? formatNumber(backtest.metrics.average_r, 2) : '—',
                  ready: Boolean(backtest),
                  tone: backtest ? valueClass(backtest.metrics.average_r) : undefined,
                },
                {
                  id: 'dd',
                  label: 'Max DD',
                  value: backtest ? formatPercent(backtest.metrics.maximum_drawdown) : '—',
                  ready: Boolean(backtest),
                  tone: undefined as string | undefined,
                },
              ].map((row) => (
                <li key={row.id} className={row.ready ? 'is-ready' : ''}>
                  <span className={`research-similar-check ${row.ready ? 'is-on' : ''}`} aria-hidden="true" />
                  <span className="research-evaluate-metric-label">{row.label}</span>
                  <strong className={row.tone}>{row.value}</strong>
                </li>
              ))}
            </ul>
            {!backtest ? (
              <p className="field-hint">Run backtest to fill Win rate, Trade count, Avg R, and Max DD.</p>
            ) : null}
          </aside>

          <aside className="research-side-card research-evaluate-interpreter ai-prose">
            <h3>
              <span className="research-ico research-ico-help" aria-hidden="true" />
              Backtest interpreter
              {backtest?.interpretation_provider === 'llm' ||
              backtest?.interpretation_provider === 'gemini' ? (
                <span className="ai-polished-badge">AI-polished</span>
              ) : null}
            </h3>
            <ul className="research-evaluate-bullets">
              {(backtest
                ? backtestInterp.bullets
                : [
                    `${displaySym} backtest parameters analyzed.`,
                    'Simulated historical data reviewed.',
                    'Never invents trades.',
                  ]
              ).map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
            <p className="research-evaluate-refuse" aria-label="Refused suggestion">
              <s>{backtestInterp.refused}</s>
            </p>
          </aside>

          <p className="research-evaluate-disclaimer">
            Disclaimer: Simulated results do not guarantee future performance.
          </p>
        </div>
      )}

      {evalResult?.has_setup && evalResult.candidate && tab === 'overview' ? (
        <p className="field-hint research-plan-strip">
          Plan · {directionLabel(evalResult.candidate.direction)} · Entry{' '}
          {formatPrice(evalResult.candidate.entry_price)} · Stop{' '}
          {formatPrice(evalResult.candidate.stop_loss)} · Target{' '}
          {formatPrice(evalResult.candidate.target)}
        </p>
      ) : null}
    </section>
  )
}
