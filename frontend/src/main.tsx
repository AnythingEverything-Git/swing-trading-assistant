import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'
import { LiveValue } from './components/LiveValue'
import { SetupChart, type ChartCandle } from './components/SetupChart'
import { StockDetailDrawer } from './components/StockDetailDrawer'
import { TradeDurationTimer } from './components/TradeDurationTimer'
import {
  PAPER_CLAIM,
  computePaperCapital,
  directionLabel,
  exitReasonLabel,
  formingStageLabel,
  paperStatusLabel,
} from './terminology'

type ThemeMode = 'light' | 'dark'

const THEME_STORAGE_KEY = 'tradepilot-theme'
const RISK_STORAGE_KEY = 'tradepilot-risk-profile'
const PAPER_ENABLED_KEY = 'tradepilot-paper-enabled'

function readStoredRisk(): { equity: string; riskPercent: string } {
  try {
    const raw = localStorage.getItem(RISK_STORAGE_KEY)
    if (!raw) return { equity: '200000', riskPercent: '1' }
    const parsed = JSON.parse(raw) as { equity?: string; riskPercent?: string }
    return {
      equity: parsed.equity || '200000',
      riskPercent: parsed.riskPercent || '1',
    }
  } catch {
    return { equity: '200000', riskPercent: '1' }
  }
}

function readStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function formatPrice(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function formatNumber(value: string | number | null | undefined, digits = 2): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(numeric)
}

function formatRatio(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${formatNumber(numeric, 2)}x`
}

function formatPercent(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${formatNumber(numeric, 2)}%`
}

function formatVolume(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(numeric)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function formatBarRef(index: number, time: string): { bar: string; when: string } {
  return {
    bar: `#${index}`,
    when: formatDateTime(time),
  }
}

type Candidate = {
  symbol: string
  timeframe: string
  direction: string
  entry_price: string | number
  stop_loss: string | number
  target: string | number
  risk_per_share: string | number
  reward: string | number
  risk_reward_ratio: string | number
  setup_name: string
}

type Evidence = {
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

type StrategyResponse = {
  has_setup: boolean
  candidate: Candidate | null
  evidence: Evidence | null
  status: string
  reason?: string | null
}

type BacktestTrade = {
  entry_time: string
  entry_price: string | number
  exit_time: string
  exit_price: string | number
  quantity: number
  risk_amount: string | number
  pnl: string | number
  exit_reason: string
}

type BacktestResponse = {
  symbol: string
  timeframe: string
  completed_trades: number
  trades: BacktestTrade[]
  metrics: {
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: string | number
    total_pnl: string | number
    average_pnl: string | number
    total_r: string | number
    average_r: string | number
    maximum_drawdown: string | number
  }
}

type Opportunity = {
  symbol: string
  candidate: Candidate
  evidence: Evidence
  quality_score?: string | number | null
  rank?: number | null
  quantity?: number | null
  risk_amount?: string | number | null
  narrative?: string | null
  invalidation?: string | null
  quality_reason?: string | null
  current_price?: string | number | null
  current_price_change_percent?: string | number | null
}

type FormingSetup = {
  symbol: string
  timeframe: string
  stage: string
  resistance: string | number
  breakout_candle_index: number
  breakout_candle_time: string
  breakout_volume: number | null
  atr_value: string | number
  volume_sma_value: string | number
  bars_elapsed: number
  bars_remaining: number
  reason: string
  narrative?: string | null
  retest_candle_index?: number | null
  retest_candle_time?: string | null
  retest_low?: string | number | null
  direction?: string
  structure_label?: string | null
  retest_label?: string | null
  current_price?: string | number | null
  current_price_change_percent?: string | number | null
}

type OpportunityScanResponse = {
  universe_name: string
  universe_version: string
  timeframe: string
  start: string
  end: string
  symbols_scanned: number
  eligible_count: number
  no_setup_count: number
  unavailable_count?: number
  error_count?: number
  opportunities: Opportunity[]
  issues?: { symbol: string; status: string; detail: string }[]
  scan_run_id?: number | null
  forming_count?: number
  forming?: FormingSetup[]
  top?: Opportunity[]
  data_source?: string
  data_claim?: string
  last_candle_time?: string | null
  alert_preview?: string | null
  paper_opened_count?: number
  paper_skipped_count?: number
  paper_claim?: string | null
}

type PaperTrade = {
  id: number
  scan_run_id?: number | null
  symbol: string
  direction: string
  entry_price: string | number
  stop_loss: string | number
  target: string | number
  quantity: number
  risk_amount?: string | number | null
  status: string
  opened_at: string
  closed_at?: string | null
  exit_price?: string | number | null
  exit_reason?: string | null
  last_mark_price?: string | number | null
  unrealized_pnl?: string | number | null
  realized_pnl?: string | number | null
  setup_name?: string | null
  quality_score?: string | number | null
}

type PaperBook = {
  claim: string
  trades: PaperTrade[]
  pending_count?: number
  open_count: number
  closed_count: number
  total_unrealized: string | number
  total_realized: string | number
}

type PaperOutlookItem = {
  trade_id: number
  symbol: string
  direction: string
  mark: string | number
  entry: string | number
  target: string | number
  stop: string | number
  distance_to_target: string | number
  distance_to_stop: string | number
  progress_pct: string | number
  atr14?: string | number | null
  avg_daily_range?: string | number | null
  drift_per_day?: string | number | null
  pace_per_day?: string | number | null
  estimated_trading_days?: string | number | null
  estimated_reach_at?: string | null
  confidence: string
  method: string
  summary: string
}

type ProductStatus = {
  data_source: string
  live_ready: boolean
  claim: string
  last_candle_time: string | null
  symbols_with_candles: number
  environment: string
  plug_and_play: string
}

type ScanRunSummary = {
  id: number
  started_at: string
  finished_at: string | null
  universe_name: string | null
  result_count: number
  symbols_scanned: number | null
  data_source: string | null
}

type MarketQuote = {
  symbol: string
  current_price: string | number | null
  current_price_change_percent: string | number | null
}

function csvEscape(value: string | number | null | undefined): string {
  const text = value == null ? '' : String(value)
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function downloadEligibleCsv(result: OpportunityScanResponse) {
  const header = [
    'rank',
    'symbol',
    'direction',
    'entry',
    'stop_loss',
    'target',
    'risk_reward',
    'quality_score',
    'quantity',
    'setup_name',
    'decision',
    'confirmation_time',
    'narrative',
  ]
  const rows = result.opportunities.map((item) =>
    [
      item.rank ?? '',
      item.symbol,
      item.candidate.direction,
      formatNumber(item.candidate.entry_price, 2),
      formatNumber(item.candidate.stop_loss, 2),
      formatNumber(item.candidate.target, 2),
      formatNumber(item.candidate.risk_reward_ratio, 2),
      formatNumber(item.quality_score, 2),
      item.quantity ?? '',
      item.candidate.setup_name,
      item.evidence.decision,
      formatDateTime(item.evidence.confirmation_candle_time),
      item.narrative ?? '',
    ]
      .map(csvEscape)
      .join(','),
  )
  const blob = new Blob([[header.join(','), ...rows].join('\n')], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const endDay = result.end.slice(0, 10)
  anchor.href = url
  anchor.download = `tradepilot-eligibles-${endDay}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

function valueClass(value: string | number) {
  const numericValue = Number(value)
  if (numericValue > 0) return 'value-positive'
  if (numericValue < 0) return 'value-negative'
  return 'value-neutral'
}

function decimalParts(value: string | number) {
  const [coefficient, exponentText] = String(value).toLowerCase().split('e')
  const sign = coefficient.startsWith('-') ? -1n : 1n
  const unsigned = coefficient.replace(/^[+-]/, '')
  const decimalDigits = unsigned.split('.')[1]?.length ?? 0
  const digits = unsigned.replace('.', '') || '0'
  const exponent = exponentText ? Number.parseInt(exponentText, 10) : 0
  return {
    integer: sign * BigInt(digits),
    scale: decimalDigits - exponent,
  }
}

function greatestCommonDivisor(left: bigint, right: bigint): bigint {
  let a = left < 0n ? -left : left
  let b = right < 0n ? -right : right
  while (b !== 0n) {
    const remainder = a % b
    a = b
    b = remainder
  }
  return a
}

function exactDecimalRatio(numeratorValue: string | number, denominatorValue: string | number) {
  const numeratorParts = decimalParts(numeratorValue)
  const denominatorParts = decimalParts(denominatorValue)
  if (denominatorParts.integer === 0n) return '0'

  let numerator = numeratorParts.integer
  let denominator = denominatorParts.integer
  const scaleDifference = denominatorParts.scale - numeratorParts.scale
  if (scaleDifference >= 0) numerator *= 10n ** BigInt(scaleDifference)
  else denominator *= 10n ** BigInt(-scaleDifference)

  const divisor = greatestCommonDivisor(numerator, denominator)
  numerator /= divisor
  denominator /= divisor
  if (denominator < 0n) {
    numerator = -numerator
    denominator = -denominator
  }

  let remainingDenominator = denominator
  while (remainingDenominator % 2n === 0n) remainingDenominator /= 2n
  while (remainingDenominator % 5n === 0n) remainingDenominator /= 5n
  if (remainingDenominator !== 1n) return `${numerator}/${denominator}`

  const sign = numerator < 0n ? '-' : ''
  const absoluteNumerator = numerator < 0n ? -numerator : numerator
  const integerPart = absoluteNumerator / denominator
  let remainder = absoluteNumerator % denominator
  if (remainder === 0n) return `${sign}${integerPart}`

  let fraction = ''
  while (remainder !== 0n) {
    remainder *= 10n
    fraction += String(remainder / denominator)
    remainder %= denominator
  }
  return `${sign}${integerPart}.${fraction}`
}

function tradeR(trade: BacktestTrade) {
  return exactDecimalRatio(trade.pnl, trade.risk_amount)
}

function calculateScanPositionSize(
  accountEquity: string,
  riskPercent: string,
  riskPerShare: string | number | null | undefined,
): { quantity: number | null; riskAmount: string | null } {
  const equity = Number(accountEquity)
  const risk = Number(riskPercent)
  const perShare = Number(riskPerShare)
  if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(risk) || risk <= 0) {
    return { quantity: null, riskAmount: null }
  }
  if (!Number.isFinite(perShare) || perShare <= 0) {
    return { quantity: 0, riskAmount: '0' }
  }
  const quantity = Math.floor((equity * risk) / 100 / perShare)
  return { quantity, riskAmount: String(quantity * perShare) }
}

function withPositionSizing(
  result: OpportunityScanResponse,
  accountEquity: string,
  riskPercent: string,
): OpportunityScanResponse {
  const sizeOpportunity = (item: Opportunity): Opportunity => {
    const sized = calculateScanPositionSize(
      accountEquity,
      riskPercent,
      item.candidate.risk_per_share,
    )
    return { ...item, quantity: sized.quantity, risk_amount: sized.riskAmount }
  }
  return {
    ...result,
    opportunities: result.opportunities.map(sizeOpportunity),
    top: result.top?.map(sizeOpportunity),
  }
}

type AppView = 'scan' | 'research' | 'paper'
type ScanUniverse = 'NIFTY_50' | 'NIFTY_100' | 'NIFTY_200' | 'NIFTY_500'

const SCAN_UNIVERSES: { value: ScanUniverse; label: string }[] = [
  { value: 'NIFTY_50', label: 'Nifty 50' },
  { value: 'NIFTY_100', label: 'Nifty 100' },
  { value: 'NIFTY_200', label: 'Nifty 200' },
  { value: 'NIFTY_500', label: 'Nifty 500' },
]

function App() {
  const storedRisk = readStoredRisk()
  const [theme, setTheme] = useState<ThemeMode>(() => readStoredTheme())
  const [activeView, setActiveView] = useState<AppView>('scan')
  const [scanUniverse, setScanUniverse] = useState<ScanUniverse>('NIFTY_500')
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('1d')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [accountEquity, setAccountEquity] = useState(storedRisk.equity)
  const [riskPercent, setRiskPercent] = useState(storedRisk.riskPercent)
  const [slippagePerShare, setSlippagePerShare] = useState('0')
  const [costPerTrade, setCostPerTrade] = useState('0')
  const [loading, setLoading] = useState(false)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [error, setError] = useState('')
  const [backtestError, setBacktestError] = useState('')
  const [result, setResult] = useState<StrategyResponse | null>(null)
  const [backtestResult, setBacktestResult] = useState<BacktestResponse | null>(null)
  const [scanStart, setScanStart] = useState('2025-12-07')
  const [scanEnd, setScanEnd] = useState('2026-09-03')
  const [scanLoading, setScanLoading] = useState(false)
  const [scanError, setScanError] = useState('')
  const [scanResult, setScanResult] = useState<OpportunityScanResponse | null>(null)
  const [paperBook, setPaperBook] = useState<PaperBook | null>(null)
  const [paperError, setPaperError] = useState('')
  const [paperNotice, setPaperNotice] = useState('')
  const [paperClosingId, setPaperClosingId] = useState<number | null>(null)
  const [entryAlerts, setEntryAlerts] = useState<PaperTrade[]>([])
  const [paperOutlookById, setPaperOutlookById] = useState<Record<number, PaperOutlookItem>>({})
  const [paperTradingEnabled, setPaperTradingEnabled] = useState(() => {
    try {
      return localStorage.getItem(PAPER_ENABLED_KEY) === '1'
    } catch {
      return false
    }
  })
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [selectedKind, setSelectedKind] = useState<'eligible' | 'forming'>('eligible')
  const [showAllOpportunities, setShowAllOpportunities] = useState(false)
  const [scanCriteriaCollapsed, setScanCriteriaCollapsed] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState('300')
  const [autoRefreshActive, setAutoRefreshActive] = useState(true)
  const [productStatus, setProductStatus] = useState<ProductStatus | null>(null)
  const [scanHistory, setScanHistory] = useState<ScanRunSummary[]>([])
  const [chartCandles, setChartCandles] = useState<ChartCandle[]>([])
  const [minScore, setMinScore] = useState('')
  const [researchQuote, setResearchQuote] = useState<MarketQuote | null>(null)

  const OPPORTUNITY_PAGE_SIZE = 10

  const baseUrl = useMemo(() => import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000', [])

  const paperCapital = useMemo(
    () => computePaperCapital(paperBook?.trades ?? [], Number(accountEquity) || 0),
    [paperBook?.trades, accountEquity],
  )

  const openPaperTrades = useMemo(
    () => (paperBook?.trades ?? []).filter((trade) => trade.status === 'OPEN'),
    [paperBook?.trades],
  )

  const pendingPaperTrades = useMemo(
    () => (paperBook?.trades ?? []).filter((trade) => trade.status === 'PENDING'),
    [paperBook?.trades],
  )

  const showPracticeStrip = paperTradingEnabled || openPaperTrades.length > 0 || pendingPaperTrades.length > 0

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem(
      RISK_STORAGE_KEY,
      JSON.stringify({ equity: accountEquity, riskPercent }),
    )
  }, [accountEquity, riskPercent])

  useEffect(() => {
    setScanResult((current) =>
      current ? withPositionSizing(current, accountEquity, riskPercent) : current,
    )
  }, [accountEquity, riskPercent])

  useEffect(() => {
    const loadMeta = async () => {
      try {
        const [statusResp, historyResp] = await Promise.all([
          fetch(`${baseUrl}/api/v1/product/status`),
          fetch(`${baseUrl}/api/v1/scan/runs?limit=8`),
        ])
        if (statusResp.ok) setProductStatus((await statusResp.json()) as ProductStatus)
        if (historyResp.ok) setScanHistory((await historyResp.json()) as ScanRunSummary[])
      } catch {
        /* banner stays empty until a scan */
      }
    }
    void loadMeta()
  }, [baseUrl])

  useEffect(() => {
    if (!selectedSymbol) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelectedSymbol(null)
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [selectedSymbol])

  const selectedOpportunity = useMemo(() => {
    if (!scanResult || !selectedSymbol || selectedKind !== 'eligible') return null
    return (
      scanResult.opportunities.find((item) => item.symbol === selectedSymbol) ??
      scanResult.top?.find((item) => item.symbol === selectedSymbol) ??
      null
    )
  }, [scanResult, selectedSymbol, selectedKind])

  const selectedForming = useMemo(() => {
    if (!scanResult || !selectedSymbol || selectedKind !== 'forming') return null
    return scanResult.forming?.find((item) => item.symbol === selectedSymbol) ?? null
  }, [scanResult, selectedSymbol, selectedKind])

  useEffect(() => {
    if (!selectedSymbol || !scanStart || !scanEnd) {
      setChartCandles([])
      return
    }
    const startDate = new Date(scanStart)
    const endDate = new Date(scanEnd)
    const query = new URLSearchParams({
      timeframe: '1d',
      start: startDate.toISOString(),
      end: endDate.toISOString(),
    })
    void fetch(`${baseUrl}/api/v1/market-data/candles/${encodeURIComponent(selectedSymbol)}?${query}`)
      .then((response) => (response.ok ? response.json() : []))
      .then((payload: ChartCandle[]) => setChartCandles(Array.isArray(payload) ? payload : []))
      .catch(() => setChartCandles([]))
  }, [baseUrl, selectedSymbol, scanStart, scanEnd])

  useEffect(() => {
    if (!scanResult) return
    const allSymbols = new Set<string>()
    scanResult.opportunities.forEach((item) => allSymbols.add(item.symbol))
    scanResult.forming?.forEach((item) => allSymbols.add(item.symbol))
    if (allSymbols.size === 0) return

    const refreshQuotes = async () => {
      try {
        const response = await fetch(
          `${baseUrl}/api/v1/market-data/quotes?symbols=${encodeURIComponent(Array.from(allSymbols).join(','))}`,
        )
        if (!response.ok) return
        const payload = (await response.json()) as {
          symbol: string
          current_price: string | number | null
          current_price_change_percent: string | number | null
        }[]
        const quoteBySymbol = new Map(payload.map((item) => [item.symbol, item]))
        setScanResult((current) => {
          if (!current) return current
          let changed = false
          const withQuote = <T extends { symbol: string; current_price?: string | number | null; current_price_change_percent?: string | number | null }>(item: T): T => {
            const quote = quoteBySymbol.get(item.symbol)
            if (!quote) return item
            if (
              String(item.current_price ?? '') === String(quote.current_price ?? '') &&
              String(item.current_price_change_percent ?? '') ===
                String(quote.current_price_change_percent ?? '')
            ) {
              return item
            }
            changed = true
            return {
              ...item,
              current_price: quote.current_price,
              current_price_change_percent: quote.current_price_change_percent,
            }
          }
          const opportunities = current.opportunities.map((item) => withQuote(item))
          const top = current.top?.map((item) => withQuote(item))
          const forming = current.forming?.map((item) => withQuote(item))
          if (!changed) return current
          return {
            ...current,
            opportunities,
            top,
            forming,
          }
        })
      } catch {
        // ignore transient quote failures
      }
    }

    void refreshQuotes()
    const timer = window.setInterval(() => {
      void refreshQuotes()
    }, 15000)
    return () => window.clearInterval(timer)
  }, [baseUrl, scanResult?.scan_run_id])

  useEffect(() => {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) {
      setResearchQuote(null)
      return
    }
    const refreshQuote = async () => {
      try {
        const response = await fetch(
          `${baseUrl}/api/v1/market-data/quotes?symbols=${encodeURIComponent(normalized)}`,
        )
        if (!response.ok) return
        const payload = (await response.json()) as MarketQuote[]
        setResearchQuote((current) => {
          const next = payload[0] ?? null
          if (
            current &&
            next &&
            String(current.current_price ?? '') === String(next.current_price ?? '') &&
            String(current.current_price_change_percent ?? '') ===
              String(next.current_price_change_percent ?? '')
          ) {
            return current
          }
          return next
        })
      } catch {
        // ignore quote failures
      }
    }
    void refreshQuote()
    const timer = window.setInterval(() => {
      void refreshQuote()
    }, 15000)
    return () => window.clearInterval(timer)
  }, [baseUrl, symbol])

  const visibleOpportunities = useMemo(() => {
    if (!scanResult) return []
    if (showAllOpportunities) return scanResult.opportunities
    return scanResult.opportunities.slice(0, OPPORTUNITY_PAGE_SIZE)
  }, [scanResult, showAllOpportunities])

  const hiddenOpportunityCount = scanResult
    ? Math.max(0, scanResult.opportunities.length - OPPORTUNITY_PAGE_SIZE)
    : 0

  const confirmationMatchesScanEnd = (opportunity: Opportunity) => {
    if (!scanResult?.end) return false
    const confirmationDay = opportunity.evidence.confirmation_candle_time.slice(0, 10)
    const endDay = scanResult.end.slice(0, 10)
    return confirmationDay === endDay
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!symbol.trim() || !timeframe.trim() || !start || !end) {
      setError('Please complete all fields before evaluating.')
      setResult(null)
      return
    }

    const startDate = new Date(start)
    const endDate = new Date(end)

    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      setError('Please enter valid date values.')
      setResult(null)
      return
    }

    if (startDate > endDate) {
      setError('Start date must be less than or equal to end date.')
      setResult(null)
      return
    }

    setLoading(true)
    setError('')

    try {
      const response = await fetch(`${baseUrl}/api/v1/strategy/evaluate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: symbol.trim(),
          timeframe,
          start: startDate.toISOString(),
          end: endDate.toISOString(),
        }),
      })

      if (!response.ok) {
        let detail = 'Request failed.'
        try {
          const payload = await response.json()
          detail = payload.detail ?? payload.message ?? detail
        } catch {
          detail = response.statusText || detail
        }
        throw new Error(detail)
      }

      const payload: StrategyResponse = await response.json()
      setResult(payload)
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Unexpected error.'
      setError(message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const handleBacktest = async () => {
    if (
      !symbol.trim() ||
      !timeframe.trim() ||
      !start ||
      !end ||
      !accountEquity ||
      !riskPercent ||
      slippagePerShare === '' ||
      costPerTrade === ''
    ) {
      setBacktestError('Please complete the backtest fields before running.')
      setBacktestResult(null)
      return
    }

    const startDate = new Date(start)
    const endDate = new Date(end)
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime()) || startDate > endDate) {
      setBacktestError('Please enter a valid date range for the backtest.')
      setBacktestResult(null)
      return
    }

    setBacktestLoading(true)
    setBacktestError('')
    try {
      const response = await fetch(`${baseUrl}/api/v1/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: symbol.trim(),
          timeframe,
          start: startDate.toISOString(),
          end: endDate.toISOString(),
          account_equity: accountEquity,
          risk_percent: riskPercent,
          slippage_per_share: slippagePerShare,
          cost_per_trade: costPerTrade,
        }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail ?? 'Backtest request failed.')
      }

      setBacktestResult(await response.json() as BacktestResponse)
    } catch (caughtError) {
      setBacktestError(caughtError instanceof Error ? caughtError.message : 'Unexpected error.')
      setBacktestResult(null)
    } finally {
      setBacktestLoading(false)
    }
  }

  const refreshPaperBook = useCallback(async () => {
    if (!paperTradingEnabled) return
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/trades?status=ALL`)
      if (!response.ok) throw new Error('Failed to load practice trades')
      setPaperBook((await response.json()) as PaperBook)
      setPaperError('')
    } catch (caught) {
      setPaperError(caught instanceof Error ? caught.message : 'Practice book unavailable')
    }
  }, [baseUrl, paperTradingEnabled])

  const refreshPaperOutlook = useCallback(async () => {
    if (!paperTradingEnabled) return
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/outlook`)
      if (!response.ok) return
      const payload = (await response.json()) as { items: PaperOutlookItem[] }
      const next: Record<number, PaperOutlookItem> = {}
      for (const item of payload.items ?? []) {
        next[item.trade_id] = item
      }
      setPaperOutlookById(next)
    } catch {
      /* outlook is best-effort */
    }
  }, [baseUrl, paperTradingEnabled])

  const tickPaperBook = useCallback(async () => {
    if (!paperTradingEnabled) return
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/tick`, { method: 'POST' })
      if (!response.ok) return
      const payload = (await response.json()) as {
        open_trades: PaperTrade[]
        pending_trades?: PaperTrade[]
        filled_this_tick?: PaperTrade[]
        closed_this_tick: PaperTrade[]
        total_unrealized: string | number
      }
      const notes: string[] = []
      const filled = payload.filled_this_tick ?? []
      if (filled.length) {
        setEntryAlerts((current) => {
          const known = new Set(current.map((t) => t.id))
          const fresh = filled.filter((t) => !known.has(t.id))
          return fresh.length ? [...fresh, ...current].slice(0, 8) : current
        })
        notes.push(
          `Buy/sell price reached: ${filled.map((t) => t.symbol).join(', ')} — start your real trade now`,
        )
        try {
          if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
            void Notification.requestPermission()
          }
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            for (const trade of filled) {
              new Notification(`Start real trade: ${trade.symbol}`, {
                body: `${directionLabel(trade.direction)} at ${formatPrice(trade.entry_price)} · safety ${formatPrice(trade.stop_loss)} · goal ${formatPrice(trade.target)}`,
              })
            }
          }
        } catch {
          /* notifications optional */
        }
      }
      if (payload.closed_this_tick?.length) {
        notes.push(
          `Finished: ${payload.closed_this_tick
            .map((t) => `${t.symbol} (${exitReasonLabel(t.exit_reason)})`)
            .join(', ')}`,
        )
      }
      await refreshPaperBook()
      await refreshPaperOutlook()
      if (notes.length) {
        const closedPnL = (payload.closed_this_tick ?? []).reduce(
          (sum, t) => sum + Number(t.realized_pnl ?? 0),
          0,
        )
        if ((payload.closed_this_tick?.length ?? 0) > 0) {
          notes.push(`Locked-in P/L this update: ${formatPrice(closedPnL)}`)
        }
        setPaperNotice(notes.join(' · '))
      }
    } catch {
      /* ignore transient tick failures */
    }
  }, [baseUrl, paperTradingEnabled, refreshPaperBook, refreshPaperOutlook])

  const dismissEntryAlert = (tradeId: number) => {
    setEntryAlerts((current) => current.filter((trade) => trade.id !== tradeId))
  }

  const dismissAllEntryAlerts = () => setEntryAlerts([])

  const closePaperTrade = async (tradeId: number) => {
    setPaperClosingId(tradeId)
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/trades/${tradeId}/close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || 'Close failed')
      }
      setPaperNotice('Practice trade updated — remaining capital refreshed below')
      await refreshPaperBook()
    } catch (caught) {
      setPaperError(caught instanceof Error ? caught.message : 'Close failed')
    } finally {
      setPaperClosingId(null)
    }
  }

  const setPaperEnabled = (enabled: boolean) => {
    setPaperTradingEnabled(enabled)
    try {
      localStorage.setItem(PAPER_ENABLED_KEY, enabled ? '1' : '0')
    } catch {
      /* ignore */
    }
  }


  const handleScan = async () => {
    if (!scanStart || !scanEnd) {
      setScanError('Please complete the scan date range before scanning.')
      setScanResult(null)
      setSelectedSymbol(null)
      return
    }

    const startDate = new Date(scanStart)
    const endDate = new Date(scanEnd)
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      setScanError('Please enter valid date values.')
      setScanResult(null)
      setSelectedSymbol(null)
      return
    }
    if (startDate > endDate) {
      setScanError('Start date must be less than or equal to end date.')
      setScanResult(null)
      setSelectedSymbol(null)
      return
    }

    setScanLoading(true)
    setScanError('')
    try {
      const response = await fetch(`${baseUrl}/api/v1/scan/opportunities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe: scanUniverse,
          timeframe: '1d',
          start: startDate.toISOString(),
          end: endDate.toISOString(),
          account_equity: accountEquity || undefined,
          risk_percent: riskPercent || '1',
          top_n: 5,
          min_score: minScore || undefined,
          enable_paper_trading: paperTradingEnabled,
        }),
      })

      if (!response.ok) {
        let detail = 'Scan request failed.'
        try {
          const payload = await response.json()
          detail = payload.detail ?? payload.message ?? detail
        } catch {
          detail = response.statusText || detail
        }
        throw new Error(detail)
      }

      const payload: OpportunityScanResponse = await response.json()
      setScanResult(withPositionSizing(payload, accountEquity, riskPercent))
      setSelectedSymbol(null)
      setShowAllOpportunities(false)
      if (paperTradingEnabled) {
        if ((payload.paper_opened_count ?? 0) > 0) {
          setPaperNotice(
            `Watching ${payload.paper_opened_count} setup(s) for buy/sell price` +
              ((payload.paper_skipped_count ?? 0) > 0
                ? ` · skipped ${payload.paper_skipped_count} (no shares sized, or already watching/open)`
                : ''),
          )
        } else {
          setPaperNotice(
            'No new practice watches. Enter capital + max-loss % so shares can be sized, and avoid symbols already watching/open.',
          )
        }
        void refreshPaperBook()
      }
      try {
        const historyResp = await fetch(`${baseUrl}/api/v1/scan/runs?limit=8`)
        if (historyResp.ok) setScanHistory((await historyResp.json()) as ScanRunSummary[])
      } catch {
        /* ignore history refresh */
      }
    } catch (caughtError) {
      setScanError(caughtError instanceof Error ? caughtError.message : 'Unexpected error.')
      setScanResult(null)
      setSelectedSymbol(null)
    } finally {
      setScanLoading(false)
    }
  }

  const handleScanRef = useRef(handleScan)
  handleScanRef.current = handleScan

  useEffect(() => {
    if (!paperTradingEnabled) return
    void refreshPaperBook()
    void refreshPaperOutlook()
  }, [paperTradingEnabled, refreshPaperBook, refreshPaperOutlook])

  useEffect(() => {
    if (!paperTradingEnabled) return
    // Poll on every view so entry fills raise alerts and the live strip stays current.
    void tickPaperBook()
    const timer = window.setInterval(() => {
      void tickPaperBook()
    }, 15000)
    return () => window.clearInterval(timer)
  }, [paperTradingEnabled, tickPaperBook])

  // Auto-refresh scan at user-chosen interval
  useEffect(() => {
    const intervalMs = Number(refreshInterval) * 1000
    if (!autoRefreshActive || intervalMs <= 0 || !scanResult || !scanCriteriaCollapsed) return
    const timer = window.setInterval(() => {
      void handleScanRef.current()
    }, intervalMs)
    return () => window.clearInterval(timer)
  }, [autoRefreshActive, refreshInterval, scanResult?.scan_run_id, scanCriteriaCollapsed])

  // Collapse criteria after first successful scan
  useEffect(() => {
    if (scanResult) setScanCriteriaCollapsed(true)
  }, [scanResult?.scan_run_id])

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <p className="brand-mark">TradePilot AI</p>
          <p className="brand-tagline">Nifty swing setups · entry · stop · target · evidence</p>
        </div>
        <nav className="app-menu" aria-label="Primary">
          <button
            type="button"
            className={`menu-link ${activeView === 'scan' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('scan')
              setSelectedSymbol(null)
            }}
          >
            Find setups
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'research' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('research')
              setSelectedSymbol(null)
            }}
          >
            Stock research
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'paper' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('paper')
              setSelectedSymbol(null)
              void refreshPaperBook()
              void tickPaperBook()
            }}
          >
            Practice trades
          </button>
        </nav>
        <button
          type="button"
          className="theme-toggle"
          onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
        >
          <span className="theme-toggle-icon" aria-hidden="true">
            {theme === 'dark' ? '○' : '●'}
          </span>
          <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
        </button>
      </header>

      <div className={`data-banner ${productStatus?.live_ready ? 'live' : 'demo'}`}>
        <strong>{scanResult?.data_claim ?? productStatus?.claim ?? 'Demo candles — not live market data'}</strong>
        <span>
          Source {scanResult?.data_source ?? productStatus?.data_source ?? 'demo'}
          {productStatus?.last_candle_time || scanResult?.last_candle_time
            ? ` · last bar ${formatDateTime(scanResult?.last_candle_time ?? productStatus?.last_candle_time)}`
            : ''}
          {productStatus ? ` · ${productStatus.symbols_with_candles} symbols in DB` : ''}
        </span>
      </div>

      {entryAlerts.length > 0 && (
        <div className="start-trade-alert" role="alert" aria-live="assertive">
          <div className="start-trade-alert-head">
            <strong>Start real trade now</strong>
            <span>Buy/sell price reached on practice watch — place your broker order if you choose to trade.</span>
            <button type="button" className="secondary-button" onClick={dismissAllEntryAlerts}>
              Dismiss all
            </button>
          </div>
          <div className="start-trade-alert-list">
            {entryAlerts.map((trade) => (
              <div key={`alert-${trade.id}`} className="start-trade-alert-card">
                <div className="start-trade-alert-main">
                  <strong>{trade.symbol}</strong>
                  <span className={`direction-pill ${trade.direction === 'SHORT' ? 'short' : 'long'}`}>
                    {directionLabel(trade.direction)}
                  </span>
                  <span>
                    Buy/sell at <b>{formatPrice(trade.entry_price)}</b>
                  </span>
                  <span>
                    Safety <b>{formatPrice(trade.stop_loss)}</b>
                  </span>
                  <span>
                    Goal <b>{formatPrice(trade.target)}</b>
                  </span>
                  <span>
                    Shares <b>{trade.quantity}</b>
                  </span>
                </div>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => dismissEntryAlert(trade.id)}
                >
                  Got it
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {showPracticeStrip && (
        <div className="live-practice-strip" aria-live="polite">
          <div className="live-practice-strip-label">
            <strong>Live practice</strong>
            <span>
              {openPaperTrades.length > 0
                ? `${openPaperTrades.length} in trade`
                : pendingPaperTrades.length > 0
                  ? `${pendingPaperTrades.length} waiting for buy/sell price`
                  : 'No live practice trade'}
            </span>
            <span className={valueClass(paperCapital.unrealized)}>
              Open P/L {formatPrice(paperCapital.unrealized)}
            </span>
            <span>Remaining {formatPrice(paperCapital.remaining)}</span>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setActiveView('paper')
                void refreshPaperBook()
                void tickPaperBook()
              }}
            >
              Open book
            </button>
          </div>
          {openPaperTrades.length > 0 ? (
            <div className="live-practice-strip-trades">
              {openPaperTrades.slice(0, 6).map((trade) => {
                const outlook = paperOutlookById[trade.id]
                return (
                  <div key={`live-${trade.id}`} className="live-practice-chip">
                    <strong>{trade.symbol}</strong>
                    <span className={`direction-pill ${trade.direction === 'SHORT' ? 'short' : 'long'}`}>
                      {directionLabel(trade.direction)}
                    </span>
                    <TradeDurationTimer startedAt={trade.opened_at} label="Running" />
                    <span>
                      LTP{' '}
                      <LiveValue
                        value={trade.last_mark_price}
                        formatted={formatPrice(trade.last_mark_price)}
                      />
                    </span>
                    <span className={valueClass(trade.unrealized_pnl ?? 0)}>
                      P/L {formatPrice(trade.unrealized_pnl)}
                    </span>
                    {outlook?.estimated_reach_at ? (
                      <span className="live-practice-eta" title={outlook.summary}>
                        Est. profit{' '}
                        {outlook.estimated_trading_days === 0 ||
                        Number(outlook.estimated_trading_days) === 0
                          ? 'now'
                          : `~${outlook.estimated_trading_days}d · ${formatDateTime(outlook.estimated_reach_at)}`}
                      </span>
                    ) : (
                      <span className="live-practice-eta">Est. profit: analyzing…</span>
                    )}
                    {outlook && (
                      <span className="live-practice-progress" title={`${outlook.progress_pct}% toward goal`}>
                        {formatNumber(outlook.progress_pct, 0)}% to goal
                      </span>
                    )}
                  </div>
                )
              })}
              {openPaperTrades.length > 6 && (
                <span className="live-practice-more">+{openPaperTrades.length - 6} more</span>
              )}
            </div>
          ) : pendingPaperTrades.length > 0 ? (
            <div className="live-practice-strip-trades">
              {pendingPaperTrades.slice(0, 4).map((trade) => (
                <div key={`wait-${trade.id}`} className="live-practice-chip pending">
                  <strong>{trade.symbol}</strong>
                  <span>Waiting for {formatPrice(trade.entry_price)}</span>
                  <span>
                    Live{' '}
                    <LiveValue
                      value={trade.last_mark_price}
                      formatted={formatPrice(trade.last_mark_price)}
                    />
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {activeView === 'scan' && (
      <section className="panel scan-panel">
        <header className="header-block">
          <p className="eyebrow">Find setups</p>
          <h1>Swing trade ideas</h1>
          <p className="header-copy">
            Scan Nifty 50 / 100 / 200 / 500 for stocks that look ready to trade now — either buy (expect price up) or
            sell short (expect price down), after a clear break, retest, and confirmation.
          </p>
        </header>

        <form
          className="strategy-form"
          onSubmit={(event) => {
            event.preventDefault()
            void handleScan()
          }}
        >
          {scanResult && (
            <button
              type="button"
              className="collapse-toggle"
              onClick={() => setScanCriteriaCollapsed((c) => !c)}
            >
              {scanCriteriaCollapsed ? '▶ Show scan criteria' : '▼ Hide scan criteria'}
            </button>
          )}
          <div className={`scan-criteria-fields ${scanCriteriaCollapsed ? 'collapsed' : ''}`}>
          <div className="field-group">
            <label htmlFor="scan-universe">Stock list</label>
            <select
              id="scan-universe"
              value={scanUniverse}
              onChange={(event) => setScanUniverse(event.target.value as ScanUniverse)}
            >
              {SCAN_UNIVERSES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="scan-start">Start date</label>
              <input
                id="scan-start"
                type="date"
                value={scanStart}
                onChange={(event) => setScanStart(event.target.value)}
              />
            </div>
            <div className="field-group">
              <label htmlFor="scan-end">End date</label>
              <input
                id="scan-end"
                type="date"
                value={scanEnd}
                onChange={(event) => setScanEnd(event.target.value)}
              />
            </div>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="scan-equity">Your capital (₹)</label>
              <input
                id="scan-equity"
                type="number"
                min="0"
                step="0.01"
                value={accountEquity}
                onChange={(event) => setAccountEquity(event.target.value)}
              />
            </div>
            <div className="field-group">
              <label htmlFor="scan-risk">Max loss per trade (%)</label>
              <input
                id="scan-risk"
                type="number"
                min="0"
                step="0.01"
                value={riskPercent}
                onChange={(event) => setRiskPercent(event.target.value)}
              />
              <p className="field-hint">
                Used only to choose how many shares to size (max risk now{' '}
                {formatPrice((Number(accountEquity) * Number(riskPercent)) / 100)}). The list of setups stays the same.
              </p>
            </div>
          </div>


          <div className="field-group paper-opt-in">
            <label className="checkbox-label" htmlFor="scan-paper-enabled">
              <input
                id="scan-paper-enabled"
                type="checkbox"
                checked={paperTradingEnabled}
                onChange={(event) => setPaperEnabled(event.target.checked)}
              />
              <span>
                Practice trades (optional) — watch buy/sell price, then auto-exit at safety
                exit or profit goal. Fake money only.
              </span>
            </label>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="scan-timeframe">Timeframe</label>
              <input id="scan-timeframe" type="text" value="1d" readOnly disabled />
            </div>
            <div className="field-group">
              <label htmlFor="scan-min-score">Min quality score</label>
              <input
                id="scan-min-score"
                type="number"
                min="0"
                max="100"
                step="1"
                value={minScore}
                onChange={(event) => setMinScore(event.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>

          {scanHistory.length > 0 && (
            <div className="field-group">
              <label htmlFor="scan-history">Reload a previous scan</label>
              <select
                id="scan-history"
                defaultValue=""
                onChange={async (event) => {
                  const id = event.target.value
                  if (!id) return
                  const response = await fetch(`${baseUrl}/api/v1/scan/runs/${id}`)
                  if (!response.ok) return
                  const payload = (await response.json()) as OpportunityScanResponse
                  setScanResult(withPositionSizing(payload, accountEquity, riskPercent))
                  setSelectedSymbol(null)
                  setShowAllOpportunities(false)
                }}
              >
                <option value="">Select a scan run</option>
                {scanHistory.map((run) => (
                  <option key={run.id} value={run.id}>
                    #{run.id} · {run.universe_name ?? 'scan'} · {run.result_count} eligible
                  </option>
                ))}
              </select>
            </div>
          )}

          </div>{/* end scan-criteria-fields */}

          <div className="actions">
            <button type="submit" className="primary-button" disabled={scanLoading}>
              {scanLoading
                ? 'Scanning...'
                : `Scan ${SCAN_UNIVERSES.find((item) => item.value === scanUniverse)?.label ?? scanUniverse}`}
            </button>
          </div>

          {scanResult && (
            <div className="refresh-controls">
              <div className="field-group">
                <label htmlFor="refresh-interval">Auto-refresh every</label>
                <select
                  id="refresh-interval"
                  value={refreshInterval}
                  onChange={(event) => {
                    const val = event.target.value
                    setRefreshInterval(val)
                    setAutoRefreshActive(val !== '0')
                  }}
                >
                  <option value="0">Off</option>
                  <option value="30">30 seconds</option>
                  <option value="60">1 minute</option>
                  <option value="120">2 minutes</option>
                  <option value="300">5 minutes</option>
                  <option value="600">10 minutes</option>
                </select>
              </div>
              {autoRefreshActive && (
                <span className="refresh-indicator">
                  {scanCriteriaCollapsed ? '↻ Auto-refreshing' : '⏸ Paused while criteria is open'}
                </span>
              )}
            </div>
          )}

          <p className="field-hint">
            Full universe scan reads persisted daily candles and can take several seconds for larger indexes.
          </p>
        </form>

        {scanError && <div className="status error">{scanError}</div>}

        {scanResult && (
          <section className="result-card">
            <h2>{scanResult.universe_name.replace('_', ' ')}</h2>
            <div className="result-grid">
              <div>
                <strong>Universe version:</strong> {scanResult.universe_version}
              </div>
              <div>
                <strong>Timeframe:</strong> {scanResult.timeframe}
              </div>
              <div>
                <strong>Range:</strong> {formatDateTime(scanResult.start)} → {formatDateTime(scanResult.end)}
              </div>
              {scanResult.scan_run_id != null && (
                <div>
                  <strong>Scan run:</strong> #{scanResult.scan_run_id}
                </div>
              )}
            </div>

            <div className="metric-grid metric-grid-five">
              <div className="metric-card">
                <span>Stocks scanned</span>
                <strong>{scanResult.symbols_scanned}</strong>
              </div>
              <div className="metric-card metric-accent">
                <span>Ready now</span>
                <strong>{scanResult.eligible_count}</strong>
              </div>
              <div className="metric-card">
                <span>Almost ready</span>
                <strong>{scanResult.forming_count ?? 0}</strong>
              </div>
              <div className="metric-card">
                <span>No idea</span>
                <strong>{scanResult.no_setup_count}</strong>
              </div>
              <div className="metric-card">
                <span>No data</span>
                <strong>{scanResult.unavailable_count ?? 0}</strong>
              </div>
              <div className="metric-card">
                <span>Errors</span>
                <strong>{scanResult.error_count ?? 0}</strong>
              </div>
            </div>

            {(scanResult.issues?.length ?? 0) > 0 && (
              <div className="issues-box">
                <h3>Data issues</h3>
                <ul>
                  {scanResult.issues!.map((issue) => (
                    <li key={`${issue.symbol}-${issue.status}`}>
                      <strong>{issue.symbol}</strong> · {issue.status}
                      <span>{issue.detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {(scanResult.top?.length ?? 0) > 0 && (
              <div className="top-book">
                <h3>Top {scanResult.top!.length} ready ideas</h3>
                <p className="field-hint">
                  Sorted by setup quality. Each card is a ready plan: buy if you expect the price to rise, or sell
                  short if you expect it to fall.
                </p>
                <div className="top-grid">
                  {scanResult.top!.map((item) => {
                    const isShort = item.candidate.direction === 'SHORT'
                    return (
                      <button
                        type="button"
                        className={`top-card ${isShort ? 'top-card-short' : 'top-card-long'}`}
                        key={`top-${item.symbol}`}
                        onClick={() => {
                          setSelectedKind('eligible')
                          setSelectedSymbol(item.symbol)
                        }}
                      >
                        <div className="top-card-head">
                          <span className="top-rank">#{item.rank}</span>
                          <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                            {directionLabel(item.candidate.direction)}
                          </span>
                        </div>
                        <strong className="top-symbol">{item.symbol}</strong>
                        <div className="top-metric">
                          <span className="top-label">Live price</span>
                          <span className="top-value">
                            <LiveValue
                              value={item.current_price}
                              formatted={formatPrice(item.current_price)}
                            />
                          </span>
                        </div>
                        <div className="top-metric">
                          <span className="top-label">Today</span>
                          <span className={`top-value ${valueClass(item.current_price_change_percent ?? 0)}`}>
                            {formatPercent(item.current_price_change_percent)}
                          </span>
                        </div>
                        <div className="top-metric">
                          <span className="top-label">Buy/sell at</span>
                          <span className="top-value">{formatPrice(item.candidate.entry_price)}</span>
                        </div>
                        <div className="top-metric">
                          <span className="top-label">Safety exit</span>
                          <span className="top-value top-value-stop">
                            {formatPrice(item.candidate.stop_loss)}
                          </span>
                        </div>
                        <div className="top-metric">
                          <span className="top-label">Profit goal</span>
                          <span className="top-value top-value-target">
                            {formatPrice(item.candidate.target)}
                          </span>
                        </div>
                        <div className="top-metric">
                          <span className="top-label">Quality</span>
                          <span className="top-value top-value-score">
                            {formatNumber(item.quality_score, 1)}
                          </span>
                        </div>
                        {item.quantity != null && (
                          <div className="top-metric">
                            <span className="top-label">Shares</span>
                            <span className="top-value">{item.quantity}</span>
                          </div>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {scanResult.alert_preview && (
              <details className="alert-preview">
                <summary>Alert preview</summary>
                <pre>{scanResult.alert_preview}</pre>
              </details>
            )}

            <div className="confirmed-box">
              <h3>Ready to trade now</h3>
              {scanResult.eligible_count === 0 ? (
                <div className="empty-state">
                  <strong>No ready ideas</strong>
                  <span>No buy or sell-short setups matched the rules for this date range.</span>
                </div>
              ) : (
                <>
                  <div className="table-toolbar">
                    <p className="field-hint">
                      Showing {visibleOpportunities.length} of {scanResult.opportunities.length} ready stocks.
                      Click a row to see the plan in plain language.
                    </p>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => downloadEligibleCsv(scanResult)}
                    >
                      Export CSV
                    </button>
                  </div>
                  <div className="table-wrap scan-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Stock</th>
                          <th>Trade type</th>
                          <th>Buy/sell at</th>
                          <th>Live price</th>
                          <th>Today</th>
                          <th>Safety exit</th>
                          <th>Profit goal</th>
                          <th>Reward vs risk</th>
                          <th>Quality</th>
                          <th>Shares</th>
                          <th>Why this idea</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleOpportunities.map((opportunity) => {
                          const isShort = opportunity.candidate.direction === 'SHORT'
                          return (
                            <tr
                              key={opportunity.symbol}
                              className={selectedSymbol === opportunity.symbol ? 'row-selected' : undefined}
                              onClick={() => {
                                setSelectedKind('eligible')
                                setSelectedSymbol(opportunity.symbol)
                              }}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                  event.preventDefault()
                                  setSelectedSymbol(opportunity.symbol)
                                }
                              }}
                              tabIndex={0}
                              role="button"
                              aria-pressed={selectedSymbol === opportunity.symbol}
                            >
                              <td className="num-cell">{opportunity.rank ?? '—'}</td>
                              <td className="symbol-cell">{opportunity.symbol}</td>
                              <td>
                                <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                  {directionLabel(isShort ? 'SHORT' : 'LONG')}
                                </span>
                              </td>
                              <td className="num-cell">
                                {formatPrice(opportunity.candidate.entry_price)}
                              </td>
                              <td className="num-cell">
                                <LiveValue
                                  value={opportunity.current_price}
                                  formatted={formatPrice(opportunity.current_price)}
                                />
                              </td>
                              <td
                                className={`num-cell ${valueClass(
                                  opportunity.current_price_change_percent ?? 0,
                                )}`}
                              >
                                {formatPercent(opportunity.current_price_change_percent)}
                              </td>
                              <td className="num-cell">
                                {formatPrice(opportunity.candidate.stop_loss)}
                              </td>
                              <td className="num-cell">
                                {formatPrice(opportunity.candidate.target)}
                              </td>
                              <td className="num-cell">
                                {formatRatio(opportunity.candidate.risk_reward_ratio)}
                              </td>
                              <td className="num-cell">
                                {formatNumber(opportunity.quality_score, 1)}
                              </td>
                              <td className="num-cell">{opportunity.quantity ?? '—'}</td>
                              <td className="why-eligible">
                                {opportunity.narrative ?? opportunity.evidence.decision}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {hiddenOpportunityCount > 0 && (
                    <div className="see-more-row">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => setShowAllOpportunities((current) => !current)}
                      >
                        {showAllOpportunities
                          ? 'Show less'
                          : `See more (${hiddenOpportunityCount} more)`}
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>

            {(scanResult.forming?.length ?? 0) > 0 && (
              <div className="forming-box">
                <h3>Almost ready (watching)</h3>
                <p className="field-hint">
                  These stocks are close, but not confirmed yet — no buy/sell price, safety exit, or profit goal
                  until the last step completes.
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Stock</th>
                        <th>Trade type</th>
                        <th>Stage</th>
                        <th>Live price</th>
                        <th>Today</th>
                        <th>Key level</th>
                        <th>Days left</th>
                        <th>Why</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scanResult.forming!.map((item) => {
                        const isShort = (item.direction ?? 'LONG') === 'SHORT'
                        return (
                          <tr
                            key={`forming-${item.symbol}`}
                            onClick={() => {
                              setSelectedKind('forming')
                              setSelectedSymbol(item.symbol)
                            }}
                            tabIndex={0}
                            role="button"
                          >
                            <td className="symbol-cell">{item.symbol}</td>
                            <td>
                              <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                {directionLabel(item.direction)}
                              </span>
                            </td>
                            <td>{formingStageLabel(item.stage)}</td>
                            <td className="num-cell">
                              <LiveValue
                                value={item.current_price}
                                formatted={formatPrice(item.current_price)}
                              />
                            </td>
                            <td
                              className={`num-cell ${valueClass(item.current_price_change_percent ?? 0)}`}
                            >
                              {formatPercent(item.current_price_change_percent)}
                            </td>
                            <td className="num-cell">{formatPrice(item.resistance)}</td>
                            <td className="num-cell">{item.bars_remaining}</td>
                            <td className="why-eligible">{item.narrative ?? item.reason}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {paperTradingEnabled && (
            <div className="paper-box">
              <div className="paper-banner">
                <strong>{PAPER_CLAIM}</strong>
                <span>
                  Waits for live price to reach buy/sell price, then auto-closes at safety exit or profit goal · no
                  fees modeled
                </span>
              </div>
              {paperNotice && <div className="status ok">{paperNotice}</div>}
              {paperError && <div className="status error">{paperError}</div>}
              <div className="paper-capital-strip">
                <div>
                  <span>Starting capital</span>
                  <strong>{formatPrice(paperCapital.starting)}</strong>
                </div>
                <div>
                  <span>Invested (in trades)</span>
                  <strong>{formatPrice(paperCapital.invested)}</strong>
                </div>
                <div className="paper-capital-remaining">
                  <span>Remaining capital</span>
                  <strong className={valueClass(paperCapital.remaining - paperCapital.starting)}>
                    {formatPrice(paperCapital.remaining)}
                  </strong>
                </div>
                <div>
                  <span>Account value (incl. open P/L)</span>
                  <strong className={valueClass(paperCapital.accountValue - paperCapital.starting)}>
                    {formatPrice(paperCapital.accountValue)}
                  </strong>
                </div>
              </div>
              <div className="result-grid paper-summary-grid">
                <div>
                  <strong>Waiting:</strong> {paperBook?.pending_count ?? 0}
                </div>
                <div>
                  <strong>In trade:</strong> {paperBook?.open_count ?? 0}
                </div>
                <div>
                  <strong>Open P/L:</strong>{' '}
                  <span className={valueClass(paperBook?.total_unrealized ?? 0)}>
                    {formatPrice(paperBook?.total_unrealized)}
                  </span>
                </div>
                <div>
                  <strong>Finished:</strong> {paperBook?.closed_count ?? 0}
                </div>
                <div>
                  <strong>Locked-in P/L:</strong>{' '}
                  <span className={valueClass(paperBook?.total_realized ?? 0)}>
                    {formatPrice(paperBook?.total_realized)}
                  </span>
                </div>
              </div>
              <div className="table-toolbar">
                <h3>Waiting for buy/sell price</h3>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    void tickPaperBook()
                  }}
                >
                  Update prices
                </button>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Stock</th>
                      <th>Trade type</th>
                      <th>Shares</th>
                      <th>Buy/sell at</th>
                      <th>Safety exit</th>
                      <th>Profit goal</th>
                      <th>Live price</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(paperBook?.trades.filter((t) => t.status === 'PENDING') ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={9} className="field-hint">
                          No watches yet. With practice mode on, a scan adds setups here until live price hits
                          buy/sell.
                        </td>
                      </tr>
                    ) : (
                      paperBook!.trades
                        .filter((t) => t.status === 'PENDING')
                        .map((trade) => {
                          const isShort = trade.direction === 'SHORT'
                          return (
                            <tr key={`pending-scan-${trade.id}`}>
                              <td className="symbol-cell">{trade.symbol}</td>
                              <td>
                                <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                  {directionLabel(isShort ? 'SHORT' : 'LONG')}
                                </span>
                              </td>
                              <td className="num-cell">{trade.quantity}</td>
                              <td className="num-cell">{formatPrice(trade.entry_price)}</td>
                              <td className="num-cell top-value-stop">{formatPrice(trade.stop_loss)}</td>
                              <td className="num-cell top-value-target">{formatPrice(trade.target)}</td>
                              <td className="num-cell">
                                <LiveValue
                                  value={trade.last_mark_price}
                                  formatted={formatPrice(trade.last_mark_price)}
                                />
                              </td>
                              <td>{paperStatusLabel(trade.status)}</td>
                              <td>
                                <button
                                  type="button"
                                  className="secondary-button"
                                  disabled={paperClosingId === trade.id}
                                  onClick={(event) => {
                                    event.stopPropagation()
                                    void closePaperTrade(trade.id)
                                  }}
                                >
                                  {paperClosingId === trade.id ? 'Working…' : 'Cancel watch'}
                                </button>
                              </td>
                            </tr>
                          )
                        })
                    )}
                  </tbody>
                </table>
              </div>
              <div className="table-toolbar">
                <h3>In trade now</h3>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Stock</th>
                      <th>Trade type</th>
                      <th>Shares</th>
                      <th>Buy/sell at</th>
                      <th>Safety exit</th>
                      <th>Profit goal</th>
                      <th>Live price</th>
                      <th>Open P/L</th>
                      <th>Running</th>
                      <th>Est. profit by</th>
                      <th>Money at risk</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(paperBook?.trades.filter((t) => t.status === 'OPEN') ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={12} className="field-hint">
                          No open practice trades yet. When practice mode is on, run a scan — trades start only after live price hits buy/sell.
                        </td>
                      </tr>
                    ) : (
                      paperBook!.trades
                        .filter((t) => t.status === 'OPEN')
                        .map((trade) => {
                          const isShort = trade.direction === 'SHORT'
                          const outlook = paperOutlookById[trade.id]
                          return (
                            <React.Fragment key={trade.id}>
                            <tr>
                              <td className="symbol-cell">{trade.symbol}</td>
                              <td>
                                <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                  {directionLabel(isShort ? 'SHORT' : 'LONG')}
                                </span>
                              </td>
                              <td className="num-cell">{trade.quantity}</td>
                              <td className="num-cell">{formatPrice(trade.entry_price)}</td>
                              <td className="num-cell top-value-stop">{formatPrice(trade.stop_loss)}</td>
                              <td className="num-cell top-value-target">{formatPrice(trade.target)}</td>
                              <td className="num-cell">
                                <LiveValue
                                  value={trade.last_mark_price}
                                  formatted={formatPrice(trade.last_mark_price)}
                                />
                              </td>
                              <td className={`num-cell ${valueClass(trade.unrealized_pnl ?? 0)}`}>
                                {formatPrice(trade.unrealized_pnl)}
                              </td>
                              <td>
                                <TradeDurationTimer startedAt={trade.opened_at} label="" />
                              </td>
                              <td className="eta-cell">
                                {outlook?.estimated_reach_at
                                  ? Number(outlook.estimated_trading_days) === 0
                                    ? 'Now'
                                    : `${formatDateTime(outlook.estimated_reach_at)} (~${outlook.estimated_trading_days}d)`
                                  : 'Analyzing…'}
                                {outlook && (
                                  <div className="eta-progress-track" title={`${outlook.progress_pct}% to goal`}>
                                    <div
                                      className="eta-progress-fill"
                                      style={{ width: `${Math.min(100, Math.max(0, Number(outlook.progress_pct) || 0))}%` }}
                                    />
                                  </div>
                                )}
                              </td>
                              <td className="num-cell">{formatPrice(trade.risk_amount)}</td>
                              <td>
                                <button
                                  type="button"
                                  className="secondary-button"
                                  disabled={paperClosingId === trade.id}
                                  onClick={(event) => {
                                    event.stopPropagation()
                                    void closePaperTrade(trade.id)
                                  }}
                                >
                                  {paperClosingId === trade.id ? 'Working…' : 'Close trade'}
                                </button>
                              </td>
                            </tr>
                            {outlook && (
                              <tr className="outlook-summary-row">
                                <td colSpan={12}>
                                  <p className="field-hint">{outlook.summary}</p>
                                </td>
                              </tr>
                            )}
                            </React.Fragment>
                          )
                        })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            )}
          </section>
        )}
      </section>
      )}

      {activeView === 'paper' && (
        <section className="panel">
          <header className="header-block">
            <p className="eyebrow">Practice trades</p>
            <h1>Your practice book</h1>
            <p className="header-copy">
              Optional practice mode: after a scan, we watch for the buy/sell price, then exit at the safety exit
              or profit goal. Live prices refresh about every 15 seconds. Nothing is sent to a real broker.
            </p>
          </header>

          <div className="field-group paper-opt-in">
            <label className="checkbox-label" htmlFor="paper-view-enabled">
              <input
                id="paper-view-enabled"
                type="checkbox"
                checked={paperTradingEnabled}
                onChange={(event) => {
                  setPaperEnabled(event.target.checked)
                  if (event.target.checked) {
                    void refreshPaperBook()
                    void tickPaperBook()
                  }
                }}
              />
              <span>Turn on practice trades (optional)</span>
            </label>
            <p className="field-hint">
              When on, each scan can watch ready setups. A trade starts only when live price reaches the buy/sell
              price, and finishes at the safety exit or profit goal.
            </p>
          </div>
          {!paperTradingEnabled ? (
            <div className="empty-state">
              <strong>Practice trading is off</strong>
              <span>Enable the switch above if you want fake trades after a scan. No real money is used.</span>
            </div>
          ) : (
          <>
          <div className="paper-banner">
            <strong>{PAPER_CLAIM}</strong>
            <span>
              Starts only when live price reaches buy/sell price · closes automatically at safety exit or profit
              goal
            </span>
          </div>
          {paperNotice && <div className="status ok">{paperNotice}</div>}
          {paperError && <div className="status error">{paperError}</div>}
          <div className="paper-capital-strip">
            <div>
              <span>Starting capital</span>
              <strong>{formatPrice(paperCapital.starting)}</strong>
              <em className="field-hint">From “Your capital” on Find setups</em>
            </div>
            <div>
              <span>Invested (in trades)</span>
              <strong>{formatPrice(paperCapital.invested)}</strong>
              <em className="field-hint">Buy/sell price × shares for open trades</em>
            </div>
            <div className="paper-capital-remaining">
              <span>Remaining capital</span>
              <strong className={valueClass(paperCapital.remaining - paperCapital.starting)}>
                {formatPrice(paperCapital.remaining)}
              </strong>
              <em className="field-hint">Updates when a trade finishes</em>
            </div>
            <div>
              <span>Account value</span>
              <strong className={valueClass(paperCapital.accountValue - paperCapital.starting)}>
                {formatPrice(paperCapital.accountValue)}
              </strong>
              <em className="field-hint">Remaining + invested + open P/L</em>
            </div>
          </div>
          <div className="field-row two-col paper-capital-edit">
            <div className="field-group">
              <label htmlFor="paper-starting-capital">Practice starting capital (₹)</label>
              <input
                id="paper-starting-capital"
                type="number"
                min="0"
                step="0.01"
                value={accountEquity}
                onChange={(event) => setAccountEquity(event.target.value)}
              />
              <p className="field-hint">
                Same as Find setups capital. Remaining = starting + locked-in P/L − invested.
              </p>
            </div>
          </div>
          <div className="metric-grid metric-grid-five">
            <div className="metric-card">
              <span>Waiting for price</span>
              <strong>{paperBook?.pending_count ?? 0}</strong>
            </div>
            <div className="metric-card metric-accent">
              <span>In trade</span>
              <strong>{paperBook?.open_count ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>Open P/L</span>
              <strong className={valueClass(paperBook?.total_unrealized ?? 0)}>
                {formatPrice(paperBook?.total_unrealized)}
              </strong>
            </div>
            <div className="metric-card">
              <span>Finished</span>
              <strong>{paperBook?.closed_count ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>Locked-in P/L</span>
              <strong className={valueClass(paperBook?.total_realized ?? 0)}>
                {formatPrice(paperBook?.total_realized)}
              </strong>
            </div>
          </div>
          <div className="table-toolbar">
            <h3>Waiting for buy/sell price</h3>
            <button type="button" className="secondary-button" onClick={() => void tickPaperBook()}>
              Update prices
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Trade type</th>
                  <th>Shares</th>
                  <th>Buy/sell at</th>
                  <th>Safety exit</th>
                  <th>Profit goal</th>
                  <th>Live price</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(paperBook?.trades.filter((t) => t.status === 'PENDING') ?? []).map((trade) => {
                  const isShort = trade.direction === 'SHORT'
                  return (
                    <tr key={`paper-pending-${trade.id}`}>
                      <td className="symbol-cell">{trade.symbol}</td>
                      <td>
                        <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                          {directionLabel(isShort ? 'SHORT' : 'LONG')}
                        </span>
                      </td>
                      <td className="num-cell">{trade.quantity}</td>
                      <td className="num-cell">{formatPrice(trade.entry_price)}</td>
                      <td className="num-cell">{formatPrice(trade.stop_loss)}</td>
                      <td className="num-cell">{formatPrice(trade.target)}</td>
                      <td className="num-cell">
                        <LiveValue
                          value={trade.last_mark_price}
                          formatted={formatPrice(trade.last_mark_price)}
                        />
                      </td>
                      <td>{paperStatusLabel(trade.status)}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={paperClosingId === trade.id}
                          onClick={() => void closePaperTrade(trade.id)}
                        >
                          Cancel watch
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="table-toolbar">
            <h3>In trade now</h3>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Trade type</th>
                  <th>Shares</th>
                  <th>Buy/sell at</th>
                  <th>Safety exit</th>
                  <th>Profit goal</th>
                  <th>Live price</th>
                  <th>Open P/L</th>
                  <th>Running</th>
                  <th>Est. profit by</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(paperBook?.trades.filter((t) => t.status === 'OPEN') ?? []).map((trade) => {
                  const isShort = trade.direction === 'SHORT'
                  const outlook = paperOutlookById[trade.id]
                  return (
                    <React.Fragment key={`paper-open-${trade.id}`}>
                    <tr>
                      <td className="symbol-cell">{trade.symbol}</td>
                      <td>
                        <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                          {directionLabel(isShort ? 'SHORT' : 'LONG')}
                        </span>
                      </td>
                      <td className="num-cell">{trade.quantity}</td>
                      <td className="num-cell">{formatPrice(trade.entry_price)}</td>
                      <td className="num-cell">{formatPrice(trade.stop_loss)}</td>
                      <td className="num-cell">{formatPrice(trade.target)}</td>
                      <td className="num-cell">
                        <LiveValue
                          value={trade.last_mark_price}
                          formatted={formatPrice(trade.last_mark_price)}
                        />
                      </td>
                      <td className={`num-cell ${valueClass(trade.unrealized_pnl ?? 0)}`}>
                        {formatPrice(trade.unrealized_pnl)}
                      </td>
                      <td>
                        <TradeDurationTimer startedAt={trade.opened_at} label="" />
                      </td>
                      <td className="eta-cell">
                        {outlook?.estimated_reach_at
                          ? Number(outlook.estimated_trading_days) === 0
                            ? 'Now'
                            : `${formatDateTime(outlook.estimated_reach_at)} (~${outlook.estimated_trading_days}d)`
                          : 'Analyzing…'}
                        {outlook && (
                          <div className="eta-progress-track" title={`${outlook.progress_pct}% to goal`}>
                            <div
                              className="eta-progress-fill"
                              style={{ width: `${Math.min(100, Math.max(0, Number(outlook.progress_pct) || 0))}%` }}
                            />
                          </div>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={paperClosingId === trade.id}
                          onClick={() => void closePaperTrade(trade.id)}
                        >
                          Close trade
                        </button>
                      </td>
                    </tr>
                    {outlook && (
                      <tr className="outlook-summary-row">
                        <td colSpan={11}>
                          <p className="field-hint">{outlook.summary}</p>
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          <h3>Finished practice trades</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Trade type</th>
                  <th>Shares</th>
                  <th>Buy/sell at</th>
                  <th>Exit price</th>
                  <th>Why closed</th>
                  <th>Locked-in P/L</th>
                  <th>Closed on</th>
                </tr>
              </thead>
              <tbody>
                {(paperBook?.trades.filter((t) => t.status === 'CLOSED') ?? []).map((trade) => {
                  const isShort = trade.direction === 'SHORT'
                  return (
                    <tr key={`paper-closed-${trade.id}`}>
                      <td className="symbol-cell">{trade.symbol}</td>
                      <td>
                        <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                          {directionLabel(isShort ? 'SHORT' : 'LONG')}
                        </span>
                      </td>
                      <td className="num-cell">{trade.quantity}</td>
                      <td className="num-cell">{formatPrice(trade.entry_price)}</td>
                      <td className="num-cell">{formatPrice(trade.exit_price)}</td>
                      <td>{exitReasonLabel(trade.exit_reason)}</td>
                      <td className={`num-cell ${valueClass(trade.realized_pnl ?? 0)}`}>
                        {formatPrice(trade.realized_pnl)}
                      </td>
                      <td>{trade.closed_at ? formatDateTime(trade.closed_at) : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          </>
          )}
        </section>
      )}

      {(selectedOpportunity || selectedForming) && (
        <StockDetailDrawer
          baseUrl={baseUrl}
          scanStart={scanStart}
          scanEnd={scanEnd}
          chartCandles={chartCandles}
          opportunity={selectedOpportunity}
          forming={selectedForming}
          confirmationMatchesScanEnd={(opportunity) =>
            confirmationMatchesScanEnd(opportunity as Opportunity)
          }
          onClose={() => setSelectedSymbol(null)}
          formatters={{
            formatPrice,
            formatNumber,
            formatPercent,
            formatRatio,
            formatVolume,
            formatDateTime,
            formatBarRef,
            valueClass,
          }}
        />
      )}

      {activeView === 'research' && (
      <section className="panel">
        <header className="header-block">
          <p className="eyebrow">Stock research</p>
          <h1>Look up one stock</h1>
          <p className="header-copy">Check one stock’s plan now, or test how the rules would have worked in the past with your capital settings.</p>
        </header>

        <form className="strategy-form" onSubmit={handleSubmit}>
          <div className="field-group">
            <label htmlFor="symbol">Stock symbol</label>
            <input
              id="symbol"
              type="text"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="e.g. ZYDUSLIFE"
            />
          </div>

          <div className="field-row">
            <div className="field-group">
              <label htmlFor="timeframe">Timeframe</label>
              <select id="timeframe" value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
                <option value="1d">1d</option>
                <option value="4h">4h</option>
                <option value="1h">1h</option>
              </select>
            </div>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="start">Start date</label>
              <input id="start" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
            </div>
            <div className="field-group">
              <label htmlFor="end">End date</label>
              <input id="end" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
            </div>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="account-equity">Your capital (₹)</label>
              <input
                id="account-equity"
                type="number"
                min="0"
                step="0.01"
                value={accountEquity}
                onChange={(event) => setAccountEquity(event.target.value)}
              />
            </div>
            <div className="field-group">
              <label htmlFor="risk-percent">Max loss per trade (%)</label>
              <input
                id="risk-percent"
                type="number"
                min="0"
                step="0.01"
                value={riskPercent}
                onChange={(event) => setRiskPercent(event.target.value)}
              />
            </div>
          </div>

          <div className="field-row two-col">
            <div className="field-group">
              <label htmlFor="slippage-per-share">Slippage per share</label>
              <input
                id="slippage-per-share"
                type="number"
                min="0"
                step="0.01"
                value={slippagePerShare}
                onChange={(event) => setSlippagePerShare(event.target.value)}
              />
            </div>
            <div className="field-group">
              <label htmlFor="cost-per-trade">Round-trip transaction cost</label>
              <input
                id="cost-per-trade"
                type="number"
                min="0"
                step="0.01"
                value={costPerTrade}
                onChange={(event) => setCostPerTrade(event.target.value)}
              />
            </div>
          </div>

          <div className="actions">
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? 'Checking…' : 'Check this stock'}
            </button>
            <button type="button" className="secondary-button" onClick={handleBacktest} disabled={backtestLoading}>
              {backtestLoading ? 'Testing history…' : 'Test on past data'}
            </button>
          </div>
          {researchQuote && (
            <p className="field-hint">
              Current price:{' '}
              <LiveValue
                value={researchQuote.current_price}
                formatted={formatPrice(researchQuote.current_price)}
              />{' '}
              ({formatPercent(researchQuote.current_price_change_percent)})
            </p>
          )}
        </form>

        {error && <div className="status error">{error}</div>}
        {backtestError && <div className="status error">{backtestError}</div>}

        {result && (
          <section className="result-card">
            <h2>Result</h2>
            <div className="result-grid">
              <div>
                <strong>Has setup:</strong> {String(result.has_setup)}
              </div>
              <div>
                <strong>Status:</strong> {result.status}
              </div>
              {result.reason ? (
                <div>
                  <strong>Reason:</strong> {result.reason}
                </div>
              ) : null}
            </div>

            {result.candidate && (
              <div className="section-box">
                <h3>Candidate</h3>
                <dl>
                  <div>
                    <dt>Stock</dt>
                    <dd className="plain-value">{result.candidate.symbol}</dd>
                  </div>
                  <div>
                    <dt>Timeframe</dt>
                    <dd>{result.candidate.timeframe}</dd>
                  </div>
                  <div>
                    <dt>Trade type</dt>
                    <dd>
                      <span
                        className={`direction-pill ${
                          result.candidate?.direction === 'LONG' ? 'long' : 'short'
                        }`}
                      >
                        {directionLabel(result.candidate?.direction)}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Buy/sell at</dt>
                    <dd>{formatPrice(result.candidate.entry_price)}</dd>
                  </div>
                  <div>
                    <dt>Safety exit</dt>
                    <dd>{formatPrice(result.candidate.stop_loss)}</dd>
                  </div>
                  <div>
                    <dt>Profit goal</dt>
                    <dd>{formatPrice(result.candidate.target)}</dd>
                  </div>
                  <div>
                    <dt>Risk per share</dt>
                    <dd>{formatPrice(result.candidate.risk_per_share)}</dd>
                  </div>
                  <div>
                    <dt>Reward</dt>
                    <dd>{formatPrice(result.candidate.reward)}</dd>
                  </div>
                  <div>
                    <dt>Risk/reward</dt>
                    <dd>{formatRatio(result.candidate.risk_reward_ratio)}</dd>
                  </div>
                  <div>
                    <dt>Setup</dt>
                    <dd className="plain-value">{result.candidate.setup_name}</dd>
                  </div>
                </dl>
              </div>
            )}

            {result.evidence && (
              <div className="section-box">
                <h3>Evidence</h3>
                <dl>
                  <div>
                    <dt>
                      {result.candidate?.direction === 'SHORT' ||
                      result.evidence.structure_label === 'support'
                        ? 'Floor (support)'
                        : 'Ceiling (resistance)'}
                    </dt>
                    <dd>{formatPrice(result.evidence.resistance)}</dd>
                  </div>
                  <div>
                    <dt>Breakout</dt>
                    <dd className="bar-ref">
                      <span>{formatBarRef(result.evidence.breakout_candle_index, result.evidence.breakout_candle_time).bar}</span>
                      <small>{formatBarRef(result.evidence.breakout_candle_index, result.evidence.breakout_candle_time).when}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Retest</dt>
                    <dd className="bar-ref">
                      <span>{formatBarRef(result.evidence.retest_candle_index, result.evidence.retest_candle_time).bar}</span>
                      <small>{formatBarRef(result.evidence.retest_candle_index, result.evidence.retest_candle_time).when}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Confirmation</dt>
                    <dd className="bar-ref">
                      <span>{formatBarRef(result.evidence.confirmation_candle_index, result.evidence.confirmation_candle_time).bar}</span>
                      <small>{formatBarRef(result.evidence.confirmation_candle_index, result.evidence.confirmation_candle_time).when}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>ATR</dt>
                    <dd>{formatNumber(result.evidence.atr_value, 2)}</dd>
                  </div>
                  <div>
                    <dt>Volume SMA</dt>
                    <dd>{formatVolume(result.evidence.volume_sma_value)}</dd>
                  </div>
                  <div>
                    <dt>Breakout volume</dt>
                    <dd>{formatVolume(result.evidence.breakout_volume)}</dd>
                  </div>
                  <div>
                    <dt>
                      {result.candidate?.direction === 'SHORT' ? 'Retest high' : 'Retest low'}
                    </dt>
                    <dd>{formatPrice(result.evidence.retest_low)}</dd>
                  </div>
                  <div>
                    <dt>Confirmation volume</dt>
                    <dd>{formatVolume(result.evidence.confirmation_volume)}</dd>
                  </div>
                  <div>
                    <dt>Decision</dt>
                    <dd className="evidence-decision">{result.evidence.decision}</dd>
                  </div>
                </dl>
              </div>
            )}
          </section>
        )}

        {backtestResult && (
          <section className="result-card">
            <h2>Past-data test results</h2>
            <div className="metric-grid">
              <div className="metric-card">
                <span>Total Trades</span>
                <strong>{backtestResult.metrics.total_trades}</strong>
              </div>
              <div className="metric-card">
                <span>Winning Trades</span>
                <strong>{backtestResult.metrics.winning_trades}</strong>
              </div>
              <div className="metric-card">
                <span>Losing Trades</span>
                <strong>{backtestResult.metrics.losing_trades}</strong>
              </div>
              <div className="metric-card">
                <span>Win Rate</span>
                <strong>{formatPercent(backtestResult.metrics.win_rate)}</strong>
              </div>
              <div className="metric-card">
                <span>Total P&amp;L</span>
                <strong className={valueClass(backtestResult.metrics.total_pnl)}>
                  {formatPrice(backtestResult.metrics.total_pnl)}
                </strong>
              </div>
              <div className="metric-card">
                <span>Average P&amp;L</span>
                <strong className={valueClass(backtestResult.metrics.average_pnl)}>
                  {formatPrice(backtestResult.metrics.average_pnl)}
                </strong>
              </div>
              <div className="metric-card">
                <span>Total R</span>
                <strong>{formatNumber(backtestResult.metrics.total_r, 2)}</strong>
              </div>
              <div className="metric-card">
                <span>Average R</span>
                <strong>{formatNumber(backtestResult.metrics.average_r, 2)}</strong>
              </div>
              <div className="metric-card">
                <span>Maximum Drawdown</span>
                <strong className="value-neutral">{formatPrice(backtestResult.metrics.maximum_drawdown)}</strong>
              </div>
            </div>
            {backtestResult.trades.length === 0 ? (
              <div className="empty-state">
                <strong>Test complete</strong>
                <span>No practice trades were generated for this history and capital settings.</span>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Opened</th>
                      <th>Closed</th>
                      <th>Shares</th>
                      <th>Buy/sell price</th>
                      <th>Exit price</th>
                      <th>Money at risk</th>
                      <th>P/L</th>
                      <th>R multiples</th>
                      <th>Why closed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestResult.trades.map((trade, index) => (
                      <tr key={`${trade.entry_time}-${index}`}>
                        <td>{formatDateTime(trade.entry_time)}</td>
                        <td>{formatDateTime(trade.exit_time)}</td>
                        <td className="num-cell">{formatVolume(trade.quantity)}</td>
                        <td className="num-cell">{formatPrice(trade.entry_price)}</td>
                        <td className="num-cell">{formatPrice(trade.exit_price)}</td>
                        <td className="num-cell">{formatPrice(trade.risk_amount)}</td>
                        <td className={`num-cell ${valueClass(trade.pnl)}`}>{formatPrice(trade.pnl)}</td>
                        <td className={`num-cell ${valueClass(trade.pnl)}`}>{tradeR(trade)}</td>
                        <td>{trade.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </section>
      )}
      <p className="disclaimer">
        Educational decision support only. TradePilot does not place orders and is not investment advice.
        Live market claims require MARKET_DATA_SOURCE=upstox and a valid Upstox token.
      </p>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
