import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'
import { LiveValue } from './components/LiveValue'
import type { ChartCandle } from './components/SetupChart'
import { StockDetailDrawer } from './components/StockDetailDrawer'
import { InspectPlanDesk } from './components/InspectPlanDesk'
import { ChartEvidenceDesk } from './components/ChartEvidenceDesk'
import { FormingWatchlistDesk } from './components/FormingWatchlistDesk'
import { PracticeFromScanDesk } from './components/PracticeFromScanDesk'
import { ScanHistoryDesk, scanCoveragePct } from './components/ScanHistoryDesk'
import {
  HeaderFilterSelect,
  HeaderSortFilter,
  SortHeaderButton,
} from './components/TableHeaderControls'
import { TradeDurationTimer } from './components/TradeDurationTimer'
import { IntradayDesk } from './components/IntradayDesk'
import { HomeHub } from './components/HomeHub'
import { PracticeBook } from './components/PracticeBook'
import { ResearchDesk } from './components/ResearchDesk'
import { AccountShell } from './components/AccountShell'
import { BriefCenter } from './components/BriefCenter'
import { CompareNamesDesk } from './components/CompareNamesDesk'
import { CapitalRisk } from './components/CapitalRisk'
import { GuidedProMode } from './components/GuidedProMode'
import { DataReadinessBanner } from './components/DataReadinessBanner'
import { FilterBuilder, DEFAULT_FILTERS, filtersToPayload, type UniverseFilterState } from './components/FilterBuilder'
import { FilterPresets } from './components/FilterPresets'
import { CoverageDrawer } from './components/CoverageDrawer'
import {
  FindSetupsCriteriaBar,
  FindSetupsResultsLayout,
  countActiveFilters,
} from './components/FindSetupsDesk'
import { UniversePicker, type ScanUniverse } from './components/UniversePicker'
import { buildPlanDeductionSteps } from './planDeduction'
import {
  getScanRun,
  isCompletedScan,
  listScanRuns,
  readDeepLinkParams,
  runScanAndWait,
} from './scan/api'
import {
  DEFAULT_FORMING_CONTROLS,
  DEFAULT_RESULT_CONTROLS,
  filterAndSortForming,
  filterAndSortOpportunities,
  nextSortState,
  strategyConfidencePercent,
  type DirectionFilter,
  type FormingControls,
  type FormingSortKey,
  type FormingStageFilter,
  type ResultControls,
  type ResultSortKey,
} from './scan/resultControls'
import type {
  Candidate,
  Evidence,
  FormingSetup,
  Opportunity,
  OpportunityScanResponse,
  ScanRunSummary,
} from './scan/types'
import {
  PAPER_CLAIM,
  computePaperCapital,
  directionLabel,
  exitReasonLabel,
  formingStageLabel,
  paperStatusLabel,
  strategyConfidenceHint,
  strategyConfidenceLabel,
} from './terminology'

type ThemeMode = 'light' | 'dark' | 'system'

const THEME_STORAGE_KEY = 'tradepilot-theme'
const RISK_STORAGE_KEY = 'tradepilot-risk-profile'
const PAPER_ENABLED_KEY = 'tradepilot-paper-enabled'
const AUTO_REFRESH_STORAGE_KEY = 'tradepilot-auto-refresh'
const REFRESH_PREFS_KEY = 'tradepilot-refresh-prefs'

function readStoredRisk(): {
  swingEquity: string
  intradayEquity: string
  riskPercent: string
} {
  try {
    const raw = localStorage.getItem(RISK_STORAGE_KEY)
    if (!raw) {
      return { swingEquity: '200000', intradayEquity: '1000000', riskPercent: '1' }
    }
    const parsed = JSON.parse(raw) as {
      equity?: string
      swingEquity?: string
      intradayEquity?: string
      riskPercent?: string
    }
    const legacy = parsed.equity || '200000'
    return {
      swingEquity: parsed.swingEquity || legacy,
      intradayEquity: parsed.intradayEquity || legacy || '1000000',
      riskPercent: parsed.riskPercent || '1',
    }
  } catch {
    return { swingEquity: '200000', intradayEquity: '1000000', riskPercent: '1' }
  }
}

function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'light' || mode === 'dark') return mode
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function readStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  return 'system'
}

function readRefreshPrefs(): {
  swingRefreshSec: string
  intradayRefreshSec: string
  practiceTickMode: string
} {
  try {
    const raw = localStorage.getItem(REFRESH_PREFS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<{
        swingRefreshSec: string
        intradayRefreshSec: string
        practiceTickMode: string
      }>
      return {
        swingRefreshSec: parsed.swingRefreshSec || '300',
        intradayRefreshSec: parsed.intradayRefreshSec || '30',
        practiceTickMode: parsed.practiceTickMode || 'manual',
      }
    }
  } catch {
    /* ignore */
  }
  return { swingRefreshSec: '300', intradayRefreshSec: '30', practiceTickMode: 'manual' }
}

function formatPrice(value: string | number | null | undefined): string {
  if (value == null || value === '') return '�'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '�'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function formatNumber(value: string | number | null | undefined, digits = 2): string {
  if (value == null || value === '') return '�'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '�'
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(numeric)
}

function formatRatio(value: string | number | null | undefined): string {
  if (value == null || value === '') return '�'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '�'
  return `${formatNumber(numeric, 2)}x`
}

function formatPercent(value: string | number | null | undefined): string {
  if (value == null || value === '') return '�'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '�'
  return `${formatNumber(numeric, 2)}%`
}

function formatVolume(value: string | number | null | undefined): string {
  if (value == null || value === '') return '�'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '�'
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(numeric)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '�'
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
  interpretation?: string | null
  interpretation_provider?: string | null
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
  symbols_with_1m?: number
  last_1m_candle_time?: string | null
  stale_risk?: string
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

function downloadEligibleCsv(
  result: OpportunityScanResponse,
  opportunities: Opportunity[],
) {
  const header = [
    'rank',
    'symbol',
    'direction',
    'entry',
    'stop_loss',
    'target',
    'risk_reward',
    'strategy_confidence_pct',
    'quality_score',
    'quantity',
    'setup_name',
    'decision',
    'confirmation_time',
    'narrative',
  ]
  const rows = opportunities.map((item) =>
    [
      item.rank ?? '',
      item.symbol,
      item.candidate.direction,
      formatNumber(item.candidate.entry_price, 2),
      formatNumber(item.candidate.stop_loss, 2),
      formatNumber(item.candidate.target, 2),
      formatNumber(item.candidate.risk_reward_ratio, 2),
      strategyConfidencePercent(item.quality_score) ?? '',
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
  entryPrice?: string | number | null,
): { quantity: number | null; riskAmount: string | null } {
  const equity = Number(accountEquity)
  const risk = Number(riskPercent)
  const perShare = Number(riskPerShare)
  const entry = Number(entryPrice)
  if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(risk) || risk <= 0) {
    return { quantity: null, riskAmount: null }
  }
  if (!Number.isFinite(perShare) || perShare <= 0) {
    return { quantity: 0, riskAmount: '0' }
  }
  // Risk budget sizing
  let quantity = Math.floor((equity * risk) / 100 / perShare)
  // Never size a practice trade above available equity notionally
  if (Number.isFinite(entry) && entry > 0) {
    const maxByCapital = Math.floor(equity / entry)
    quantity = Math.min(quantity, Math.max(0, maxByCapital))
  }
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
      item.candidate.entry_price,
    )
    return { ...item, quantity: sized.quantity, risk_amount: sized.riskAmount }
  }
  return {
    ...result,
    opportunities: result.opportunities.map(sizeOpportunity),
    top: result.top?.map(sizeOpportunity),
  }
}

function humanStructureLabel(direction: string, _raw?: string | null): string {
  return direction === 'SHORT' ? 'Floor (support)' : 'Ceiling (resistance)'
}

function humanRetestLabel(direction: string, _raw?: string | null): string {
  return direction === 'SHORT' ? 'Retest high' : 'Retest low'
}

function deductionStepsForOpportunity(
  opportunity: Opportunity,
  accountEquity: string,
  riskPercent: string,
) {
  return buildPlanDeductionSteps({
    symbol: opportunity.symbol,
    direction: opportunity.candidate.direction,
    entry: opportunity.candidate.entry_price,
    stop: opportunity.candidate.stop_loss,
    target: opportunity.candidate.target,
    riskPerShare: opportunity.candidate.risk_per_share,
    reward: opportunity.candidate.reward,
    riskRewardRatio: opportunity.candidate.risk_reward_ratio,
    setupName: opportunity.candidate.setup_name,
    resistance: opportunity.evidence.resistance,
    retestExtreme: opportunity.evidence.retest_low,
    atr: opportunity.evidence.atr_value,
    breakoutVolume: opportunity.evidence.breakout_volume,
    confirmationVolume: opportunity.evidence.confirmation_volume,
    volumeSma: opportunity.evidence.volume_sma_value,
    decision: opportunity.evidence.decision,
    structureLabel: humanStructureLabel(
      opportunity.candidate.direction,
      opportunity.evidence.structure_label,
    ),
    retestLabel: humanRetestLabel(
      opportunity.candidate.direction,
      opportunity.evidence.retest_label,
    ),
    qualityScore: opportunity.quality_score,
    qualityReason: opportunity.quality_reason,
    quantity: opportunity.quantity,
    riskAmount: opportunity.risk_amount,
    accountEquity,
    riskPercent,
    formatPrice,
    formatNumber,
    formatPercent,
    formatRatio,
  })
}

type AppView = 'home' | 'scan' | 'history' | 'research' | 'paper' | 'intraday' | 'practice' | 'account' | 'brief' | 'compare'

const SCAN_UNIVERSES: { value: ScanUniverse; label: string }[] = [
  { value: 'NSE_ALL', label: 'NSE all (cash + ETFs)' },
  { value: 'NSE_CASH', label: 'NSE cash' },
  { value: 'NSE_ETF', label: 'NSE ETFs' },
  { value: 'NIFTY_50', label: 'Nifty 50' },
  { value: 'NIFTY_100', label: 'Nifty 100' },
  { value: 'NIFTY_200', label: 'Nifty 200' },
  { value: 'NIFTY_500', label: 'Nifty 500' },
]

const UNIVERSE_STORAGE_KEY = 'tp_scan_universe'
const FILTERS_STORAGE_KEY = 'tp_scan_filters'

function readStoredUniverse(): ScanUniverse {
  try {
    const raw = localStorage.getItem(UNIVERSE_STORAGE_KEY)
    if (raw && SCAN_UNIVERSES.some((u) => u.value === raw)) return raw as ScanUniverse
  } catch {
    /* ignore */
  }
  return 'NIFTY_500'
}

function readStoredFilters(): UniverseFilterState {
  try {
    const raw = localStorage.getItem(FILTERS_STORAGE_KEY)
    if (!raw) return DEFAULT_FILTERS
    const parsed = JSON.parse(raw) as Partial<UniverseFilterState>
    return { ...DEFAULT_FILTERS, ...parsed, sectors: Array.isArray(parsed.sectors) ? parsed.sectors : [] }
  } catch {
    return DEFAULT_FILTERS
  }
}

function persistScanFilters(next: UniverseFilterState) {
  try {
    localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* ignore */
  }
}

function assetClassForUniverse(universe: ScanUniverse): UniverseFilterState['asset_class'] {
  if (universe === 'NSE_CASH') return 'STOCK'
  if (universe === 'NSE_ETF') return 'ETF'
  return 'ALL'
}

function App() {
  const storedRisk = readStoredRisk()
  const storedRefresh = readRefreshPrefs()
  const [theme, setTheme] = useState<ThemeMode>(() => readStoredTheme())
  const [activeView, setActiveView] = useState<AppView>('home')
  const [accountInitialTab, setAccountInitialTab] = useState<
    'risk' | 'alerts' | 'appearance' | 'export' | 'plans' | 'broker' | 'ops'
  >('risk')
  const [swingRefreshSec, setSwingRefreshSec] = useState(storedRefresh.swingRefreshSec)
  const [intradayRefreshSec, setIntradayRefreshSec] = useState(storedRefresh.intradayRefreshSec)
  const [practiceTickMode, setPracticeTickMode] = useState(storedRefresh.practiceTickMode)
  const [scanUniverse, setScanUniverse] = useState<ScanUniverse>(() => readStoredUniverse())
  const [guidedMode, setGuidedMode] = useState(() => {
    try {
      return localStorage.getItem('tp_guided') !== '0'
    } catch {
      return true
    }
  })
  const [scanFilters, setScanFilters] = useState<UniverseFilterState>(() => readStoredFilters())
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('1d')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [swingEquity, setSwingEquity] = useState(storedRisk.swingEquity)
  const [intradayEquity, setIntradayEquity] = useState(storedRisk.intradayEquity)
  const [riskPercent, setRiskPercent] = useState(storedRisk.riskPercent)
  const [capitalRiskOpen, setCapitalRiskOpen] = useState(false)
  const [universeOpen, setUniverseOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [presetsOpen, setPresetsOpen] = useState(false)
  const [coverageOpen, setCoverageOpen] = useState(false)
  const [guidedProOpen, setGuidedProOpen] = useState(false)
  const [showHowItWorks, setShowHowItWorks] = useState(false)
  const [slippagePerShare, setSlippagePerShare] = useState('0')
  const [costPerTrade, setCostPerTrade] = useState('0')
  const [loading, setLoading] = useState(false)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [error, setError] = useState('')
  const [backtestError, setBacktestError] = useState('')
  const [result, setResult] = useState<StrategyResponse | null>(null)
  const [backtestResult, setBacktestResult] = useState<BacktestResponse | null>(null)
  const [scanStart, setScanStart] = useState(() => {
    const end = new Date()
    const start = new Date()
    start.setUTCDate(start.getUTCDate() - 270)
    return start.toISOString().slice(0, 10)
  })
  const [scanEnd, setScanEnd] = useState(() => new Date().toISOString().slice(0, 10))
  const [scanLoading, setScanLoading] = useState(false)
  const [scanProgress, setScanProgress] = useState('')
  const [scanError, setScanError] = useState('')
  const [scanResult, setScanResult] = useState<OpportunityScanResponse | null>(null)
  const [paperBook, setPaperBook] = useState<PaperBook | null>(null)
  const [paperError, setPaperError] = useState('')
  const [paperNotice, setPaperNotice] = useState('')
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
  const [selectedKind, setSelectedKind] = useState<'eligible' | 'forming' | 'lookup'>('eligible')
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false)
  const [inspectPlanOpen, setInspectPlanOpen] = useState(false)
  const [chartEvidenceOpen, setChartEvidenceOpen] = useState(false)
  const [showAllOpportunities, setShowAllOpportunities] = useState(false)
  const [scanCriteriaCollapsed, setScanCriteriaCollapsed] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(() => {
    try {
      const raw = localStorage.getItem(AUTO_REFRESH_STORAGE_KEY)
      if (!raw) return '300'
      const parsed = JSON.parse(raw) as { interval?: string }
      const interval = String(parsed.interval ?? '300')
      return ['30', '60', '120', '300', '600'].includes(interval) ? interval : '300'
    } catch {
      return '300'
    }
  })
  const [autoRefreshActive, setAutoRefreshActive] = useState(() => {
    try {
      const raw = localStorage.getItem(AUTO_REFRESH_STORAGE_KEY)
      if (!raw) return true
      const parsed = JSON.parse(raw) as { enabled?: boolean }
      return parsed.enabled !== false
    } catch {
      return true
    }
  })
  const [autoRefreshSecondsLeft, setAutoRefreshSecondsLeft] = useState<number | null>(null)
  const [autoRefreshPaused, setAutoRefreshPaused] = useState(false)
  const [autoRefreshPauseReason, setAutoRefreshPauseReason] = useState<string | null>(null)
  const autoRefreshDeadlineRef = useRef<number | null>(null)
  const autoRefreshRemainingRef = useRef<number | null>(null)
  const [productStatus, setProductStatus] = useState<ProductStatus | null>(null)
  const [scanHistory, setScanHistory] = useState<ScanRunSummary[]>([])
  const [historySelectedId, setHistorySelectedId] = useState<number | null>(null)
  const [historyBusyId, setHistoryBusyId] = useState<number | null>(null)
  const [historyError, setHistoryError] = useState('')
  const [historyRefreshing, setHistoryRefreshing] = useState(false)
  const [chartCandles, setChartCandles] = useState<ChartCandle[]>([])
  const [minScore, setMinScore] = useState('')
  const [topN, setTopN] = useState('5')
  const [resultControls, setResultControls] = useState<ResultControls>(DEFAULT_RESULT_CONTROLS)
  const [formingControls, setFormingControls] = useState<FormingControls>(DEFAULT_FORMING_CONTROLS)
  const [researchQuote, setResearchQuote] = useState<MarketQuote | null>(null)

  const OPPORTUNITY_PAGE_SIZE = 10

  const baseUrl = useMemo(() => {
    const raw = import.meta.env.VITE_API_BASE_URL as string | undefined
    // Production nginx: empty string ? same-origin `/api/...`
    if (raw === '' || raw === '/') return ''
    if (raw == null || raw === undefined) return 'http://127.0.0.1:8001'
    return String(raw).replace(/\/$/, '')
  }, [])

  const paperCapital = useMemo(
    () => computePaperCapital(paperBook?.trades ?? [], Number(swingEquity) || 0),
    [paperBook?.trades, swingEquity],
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
  const scanFocusOpen = inspectPlanOpen || chartEvidenceOpen

  useEffect(() => {
    const apply = () => {
      document.documentElement.setAttribute('data-theme', resolveTheme(theme))
    }
    apply()
    localStorage.setItem(THEME_STORAGE_KEY, theme)
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => apply()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  function persistGuidedMode(next: boolean) {
    setGuidedMode(next)
    try {
      localStorage.setItem('tp_guided', next ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    localStorage.setItem(
      RISK_STORAGE_KEY,
      JSON.stringify({
        swingEquity,
        intradayEquity,
        riskPercent,
        equity: swingEquity,
      }),
    )
  }, [swingEquity, intradayEquity, riskPercent])

  useEffect(() => {
    setScanResult((current) =>
      current ? withPositionSizing(current, swingEquity, riskPercent) : current,
    )
  }, [swingEquity, riskPercent])

  useEffect(() => {
    const loadMeta = async () => {
      try {
        const statusResp = await fetch(`${baseUrl}/api/v1/product/status`)
        if (statusResp.ok) setProductStatus((await statusResp.json()) as ProductStatus)
        setScanHistory(await listScanRuns(baseUrl, 30))
      } catch {
        /* banner stays empty until a scan */
      }
    }
    void loadMeta()
  }, [baseUrl])

  useEffect(() => {
    setHistorySelectedId((current) => {
      if (current && scanHistory.some((run) => run.id === current)) return current
      return scanHistory[0]?.id ?? null
    })
  }, [scanHistory])

  async function refreshScanHistory() {
    setHistoryRefreshing(true)
    try {
      const runs = await listScanRuns(baseUrl, 30)
      setScanHistory(runs)
      setHistoryError('')
      setHistorySelectedId((current) => {
        if (current && runs.some((run) => run.id === current)) return current
        return runs[0]?.id ?? null
      })
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Failed to load scan history')
    } finally {
      setHistoryRefreshing(false)
    }
  }

  async function openScanHistoryRun(runId: number) {
    setHistoryBusyId(runId)
    setHistoryError('')
    try {
      const payload = await getScanRun(baseUrl, runId)
      if (!isCompletedScan(payload)) {
        setHistoryError(
          payload.status === 'failed'
            ? payload.error_message || 'That scan failed'
            : 'That scan is still running � try again shortly.',
        )
        return
      }
      setScanResult(withPositionSizing(payload, swingEquity, riskPercent))
      setHistorySelectedId(runId)
      setSelectedSymbol(null)
      setDetailDrawerOpen(false)
      setInspectPlanOpen(false)
      setChartEvidenceOpen(false)
      setShowAllOpportunities(false)
      setScanCriteriaCollapsed(true)
      setScanError('')
      setActiveView('scan')
      window.setTimeout(() => {
        document.getElementById('find-setups-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 80)
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Failed to open scan')
    } finally {
      setHistoryBusyId(null)
    }
  }

  async function exportScanHistoryCsv(runId: number) {
    setHistoryError('')
    try {
      const payload = await getScanRun(baseUrl, runId)
      if (!isCompletedScan(payload)) {
        setHistoryError(
          payload.status === 'failed'
            ? payload.error_message || 'That scan failed'
            : 'That scan is still running � export when it finishes.',
        )
        return
      }
      const sized = withPositionSizing(payload, swingEquity, riskPercent)
      downloadEligibleCsv(sized, sized.opportunities ?? [])
      setHistorySelectedId(runId)
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Failed to export CSV')
    }
  }
  async function refreshProductStatus() {
    const statusResp = await fetch(`${baseUrl}/api/v1/product/status`)
    if (statusResp.ok) setProductStatus((await statusResp.json()) as ProductStatus)
  }

  useEffect(() => {
    if (!detailDrawerOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [detailDrawerOpen])

  const openStockDetail = useCallback(
    (rawSymbol: string, preferred?: 'eligible' | 'forming') => {
      const next = rawSymbol.trim().toUpperCase()
      if (!next) return
      if (preferred === 'forming') {
        setSelectedKind('forming')
        setSelectedSymbol(next)
        setDetailDrawerOpen(true)
        return
      }
      if (preferred === 'eligible') {
        setSelectedKind('eligible')
        setSelectedSymbol(next)
        setDetailDrawerOpen(true)
        return
      }
      const scan = scanResult
      const inEligible = Boolean(
        scan?.opportunities.some((item) => item.symbol === next) ||
          scan?.top?.some((item) => item.symbol === next),
      )
      const inForming = Boolean(scan?.forming?.some((item) => item.symbol === next))
      if (inEligible) setSelectedKind('eligible')
      else if (inForming) setSelectedKind('forming')
      else setSelectedKind('lookup')
      setSelectedSymbol(next)
      setDetailDrawerOpen(true)
    },
    [scanResult],
  )

  useEffect(() => {
    const { view, runId, symbol: deepSymbol, tab: deepTab } = readDeepLinkParams()
    if (view === 'home' || view === '' || view == null) setActiveView('home')
    if (view === 'scan') setActiveView('scan')
    if (view === 'history') setActiveView('history')
    if (view === 'intraday') setActiveView('intraday')
    if (view === 'research') setActiveView('research')
    if (view === 'paper') setActiveView('practice')
    if (view === 'practice') setActiveView('practice')
    if (view === 'brief') setActiveView('brief')
    if (view === 'compare') setActiveView('compare')
    if (view === 'account') setActiveView('account')
    const allowedAccountTabs = new Set([
      'risk',
      'alerts',
      'appearance',
      'export',
      'plans',
      'broker',
      'ops',
    ])
    if (deepTab && allowedAccountTabs.has(deepTab)) {
      setAccountInitialTab(deepTab as typeof accountInitialTab)
    }
    if (runId == null) return
    let cancelled = false
    const loadDeepLink = async () => {
      try {
        setScanLoading(true)
        setScanProgress('Loading linked scan�')
        const payload = await getScanRun(baseUrl, runId)
        if (cancelled) return
        if (!isCompletedScan(payload)) {
          setScanError(
            payload.status === 'failed'
              ? payload.error_message || 'Linked scan failed'
              : 'Linked scan is still running � reload shortly.',
          )
          return
        }
        setScanResult(withPositionSizing(payload, swingEquity, riskPercent))
        setActiveView('scan')
        setScanCriteriaCollapsed(true)
        if (deepSymbol) {
          setSelectedKind('eligible')
          setSelectedSymbol(deepSymbol)
          setInspectPlanOpen(true)
          setChartEvidenceOpen(false)
        }
      } catch (err) {
        if (!cancelled) {
          setScanError(err instanceof Error ? err.message : 'Failed to open linked scan')
        }
      } finally {
        if (!cancelled) {
          setScanLoading(false)
          setScanProgress('')
        }
      }
    }
    void loadDeepLink()
    return () => {
      cancelled = true
    }
    // Intentionally once on mount for email deep links.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl])

  const selectedOpportunity = useMemo(() => {
    if (!scanResult || !selectedSymbol) return null
    if (selectedKind === 'forming') return null
    return (
      scanResult.opportunities.find((item) => item.symbol === selectedSymbol) ??
      scanResult.top?.find((item) => item.symbol === selectedSymbol) ??
      null
    )
  }, [scanResult, selectedSymbol, selectedKind])

  const inspectDeductionSteps = useMemo(() => {
    if (!selectedOpportunity) return []
    return deductionStepsForOpportunity(selectedOpportunity, swingEquity, riskPercent)
  }, [selectedOpportunity, swingEquity, riskPercent])

  const selectedForming = useMemo(() => {
    if (!scanResult || !selectedSymbol) return null
    if (selectedKind === 'eligible') return null
    if (selectedKind === 'forming') {
      return scanResult.forming?.find((item) => item.symbol === selectedSymbol) ?? null
    }
    // lookup: prefer opportunity path; only attach forming when no opportunity
    const hasOpp =
      scanResult.opportunities.some((item) => item.symbol === selectedSymbol) ||
      Boolean(scanResult.top?.some((item) => item.symbol === selectedSymbol))
    if (hasOpp) return null
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

  const filteredOpportunities = useMemo(() => {
    if (!scanResult) return []
    return filterAndSortOpportunities(scanResult.opportunities, resultControls)
  }, [scanResult, resultControls])

  const filteredForming = useMemo(() => {
    if (!scanResult?.forming) return []
    return filterAndSortForming(scanResult.forming, formingControls)
  }, [scanResult, formingControls])

  const topReadyIdeas = useMemo(() => {
    if (!scanResult) return []
    const cardControls: ResultControls = {
      ...resultControls,
      sortBy: 'confidence',
      sortDir: 'desc',
    }
    const ranked = filterAndSortOpportunities(scanResult.opportunities, cardControls)
    const n = Math.max(1, Math.min(50, Number(topN) || 5))
    return ranked.slice(0, n)
  }, [scanResult, resultControls, topN])

  const visibleOpportunities = useMemo(() => {
    if (showAllOpportunities) return filteredOpportunities
    return filteredOpportunities.slice(0, OPPORTUNITY_PAGE_SIZE)
  }, [filteredOpportunities, showAllOpportunities])

  const hiddenOpportunityCount = Math.max(0, filteredOpportunities.length - OPPORTUNITY_PAGE_SIZE)

  const setEligibleSort = (key: ResultSortKey, defaultDir: 'asc' | 'desc' = 'desc') => {
    setShowAllOpportunities(false)
    setResultControls((current) => ({
      ...current,
      ...nextSortState(current.sortBy, current.sortDir, key, defaultDir),
    }))
  }

  const setFormingSort = (key: FormingSortKey, defaultDir: 'asc' | 'desc' = 'asc') => {
    setFormingControls((current) => ({
      ...current,
      ...nextSortState(current.sortBy, current.sortDir, key, defaultDir),
    }))
  }

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
      !swingEquity ||
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
          account_equity: swingEquity,
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
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/trades?status=ALL`)
      if (!response.ok) {
        throw new Error(`Failed to load practice trades (HTTP ${response.status})`)
      }
      setPaperBook((await response.json()) as PaperBook)
      setPaperError('')
    } catch (caught) {
      const message =
        caught instanceof TypeError
          ? 'Cannot reach API � is the backend running on the configured URL?'
          : caught instanceof Error
            ? caught.message
            : 'Practice book unavailable'
      setPaperError(message)
    }
  }, [baseUrl])

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
          `Buy/sell price reached: ${filled.map((t) => t.symbol).join(', ')} � start your real trade now`,
        )
        try {
          if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
            void Notification.requestPermission()
          }
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            for (const trade of filled) {
              new Notification(`Start real trade: ${trade.symbol}`, {
                body: `${directionLabel(trade.direction)} at ${formatPrice(trade.entry_price)} � safety ${formatPrice(trade.stop_loss)} � goal ${formatPrice(trade.target)}`,
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
        setPaperNotice(notes.join(' � '))
      }
    } catch {
      /* ignore transient tick failures */
    }
  }, [baseUrl, paperTradingEnabled, refreshPaperBook, refreshPaperOutlook])

  const dismissEntryAlert = (tradeId: number) => {
    setEntryAlerts((current) => current.filter((trade) => trade.id !== tradeId))
  }

  const dismissAllEntryAlerts = () => setEntryAlerts([])

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
    const universeLabel = SCAN_UNIVERSES.find((item) => item.value === scanUniverse)?.label ?? scanUniverse
    const largeHint =
      scanUniverse === 'NSE_ALL' || scanUniverse === 'NSE_CASH'
        ? ' � large universe may take a few minutes'
        : ''
    setScanProgress(`Scanning ${universeLabel}${largeHint}�`)
    setScanError('')
    try {
      const payload = await runScanAndWait(
        baseUrl,
        {
          universe: scanUniverse,
          timeframe: '1d',
          start: startDate.toISOString(),
          end: endDate.toISOString(),
          account_equity: swingEquity || undefined,
          risk_percent: riskPercent || '1',
          top_n: Math.max(1, Math.min(50, Number(topN) || 5)),
          min_score: minScore || undefined,
          enable_paper_trading: paperTradingEnabled,
          filters: filtersToPayload(scanFilters),
        },
        {
          onStatus: (status) => {
            const label =
              SCAN_UNIVERSES.find((item) => item.value === scanUniverse)?.label ?? scanUniverse
            if (status === 'queued') setScanProgress(`Queued ${label} scan�`)
            else if (status === 'running') setScanProgress(`Scanning ${label}�`)
            else setScanProgress(`Finishing ${label}�`)
          },
        },
      )
      setScanResult(withPositionSizing(payload, swingEquity, riskPercent))
      const first =
        payload.top?.[0]?.symbol ||
        payload.opportunities?.[0]?.symbol ||
        null
      setSelectedSymbol(first)
      setSelectedKind('eligible')
      setDetailDrawerOpen(false)
      setInspectPlanOpen(false)
      setChartEvidenceOpen(false)
      setShowAllOpportunities(false)
      if (payload.scan_run_id != null) setHistorySelectedId(payload.scan_run_id)
      if (paperTradingEnabled) {
        if ((payload.paper_opened_count ?? 0) > 0) {
          setPaperNotice(
            `Watching ${payload.paper_opened_count} setup(s) for buy/sell price` +
              ((payload.paper_skipped_count ?? 0) > 0
                ? ` � skipped ${payload.paper_skipped_count} (no shares sized, or already watching/open)`
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
        setScanHistory(await listScanRuns(baseUrl, 30))
      } catch {
        /* ignore history refresh */
      }
    } catch (caughtError) {
      setScanError(caughtError instanceof Error ? caughtError.message : 'Unexpected error.')
      setScanResult(null)
      setSelectedSymbol(null)
      setDetailDrawerOpen(false)
    } finally {
      setScanLoading(false)
      setScanProgress('')
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
    if (!scanResult || scanFocusOpen) return
    void refreshPaperBook()
  }, [scanResult?.scan_run_id, scanFocusOpen, refreshPaperBook])

  useEffect(() => {
    if (!paperTradingEnabled) return
    // Poll on every view so entry fills raise alerts and the live strip stays current.
    void tickPaperBook()
    if (practiceTickMode === 'manual') return
    const ms = Math.max(5, Number(practiceTickMode) || 15) * 1000
    const timer = window.setInterval(() => {
      void tickPaperBook()
    }, ms)
    return () => window.clearInterval(timer)
  }, [paperTradingEnabled, tickPaperBook, practiceTickMode])

  useEffect(() => {
    setRefreshInterval(swingRefreshSec)
  }, [swingRefreshSec])

  useEffect(() => {
    try {
      localStorage.setItem(
        REFRESH_PREFS_KEY,
        JSON.stringify({ swingRefreshSec, intradayRefreshSec, practiceTickMode }),
      )
    } catch {
      /* ignore */
    }
  }, [swingRefreshSec, intradayRefreshSec, practiceTickMode])

  // Auto-refresh scan: countdown, pause when criteria / inspect open or off Swing
  useEffect(() => {
    try {
      localStorage.setItem(
        AUTO_REFRESH_STORAGE_KEY,
        JSON.stringify({ enabled: autoRefreshActive, interval: refreshInterval }),
      )
    } catch {
      /* ignore */
    }
  }, [autoRefreshActive, refreshInterval])

  useEffect(() => {
    autoRefreshDeadlineRef.current = null
    autoRefreshRemainingRef.current = null
    setAutoRefreshSecondsLeft(null)
  }, [refreshInterval, scanResult?.scan_run_id])

  useEffect(() => {
    const intervalMs = Number(refreshInterval) * 1000
    if (!autoRefreshActive || intervalMs <= 0 || !scanResult) {
      autoRefreshDeadlineRef.current = null
      autoRefreshRemainingRef.current = null
      setAutoRefreshSecondsLeft(null)
      setAutoRefreshPaused(false)
      setAutoRefreshPauseReason(null)
      return
    }

    const tick = () => {
      let pauseReason: string | null = null
      if (activeView !== 'scan') pauseReason = 'Paused off Swing'
      else if (!scanCriteriaCollapsed) pauseReason = 'Paused � criteria panel open'
      else if (scanFocusOpen) pauseReason = 'Paused while inspecting a plan'
      else if (scanLoading) pauseReason = 'Scan in progress'

      if (pauseReason) {
        if (autoRefreshDeadlineRef.current != null) {
          autoRefreshRemainingRef.current = Math.max(0, autoRefreshDeadlineRef.current - Date.now())
          autoRefreshDeadlineRef.current = null
        }
        setAutoRefreshPaused(true)
        setAutoRefreshPauseReason(pauseReason)
        const rem = autoRefreshRemainingRef.current
        setAutoRefreshSecondsLeft(rem != null ? Math.ceil(rem / 1000) : Math.ceil(intervalMs / 1000))
        return
      }

      setAutoRefreshPaused(false)
      setAutoRefreshPauseReason(null)
      if (autoRefreshDeadlineRef.current == null) {
        const remaining = autoRefreshRemainingRef.current ?? intervalMs
        autoRefreshDeadlineRef.current = Date.now() + remaining
        autoRefreshRemainingRef.current = null
      }
      const leftMs = autoRefreshDeadlineRef.current - Date.now()
      if (leftMs <= 0) {
        autoRefreshDeadlineRef.current = Date.now() + intervalMs
        setAutoRefreshSecondsLeft(Math.ceil(intervalMs / 1000))
        void handleScanRef.current()
        return
      }
      setAutoRefreshSecondsLeft(Math.ceil(leftMs / 1000))
    }

    tick()
    const timer = window.setInterval(tick, 250)
    return () => window.clearInterval(timer)
  }, [
    autoRefreshActive,
    refreshInterval,
    scanResult?.scan_run_id,
    scanCriteriaCollapsed,
    scanFocusOpen,
    activeView,
    scanLoading,
  ])

  // Collapse criteria after first successful scan
  useEffect(() => {
    if (scanResult) setScanCriteriaCollapsed(true)
  }, [scanResult?.scan_run_id])

  return (
    <main className="app-shell">
      <header className="top-bar wireframe-topbar">
        <button
          type="button"
          className="brand-block brand-home"
          onClick={() => setActiveView('home')}
        >
          <p className="brand-mark">TradePilot</p>
        </button>
        <nav className="app-menu" aria-label="Primary">
          <button
            type="button"
            className={`menu-link ${activeView === 'scan' || activeView === 'history' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('scan')
              setSelectedSymbol(null)
              setDetailDrawerOpen(false)
              setInspectPlanOpen(false)
              setChartEvidenceOpen(false)
            }}
          >
            Swing
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'intraday' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('intraday')
              setSelectedSymbol(null)
              setDetailDrawerOpen(false)
            }}
          >
            Intraday
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'research' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('research')
              setSelectedSymbol(null)
              setDetailDrawerOpen(false)
            }}
          >
            Research
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'brief' ? 'active' : ''}`}
            onClick={() => setActiveView('brief')}
          >
            Brief
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'practice' || activeView === 'paper' ? 'active' : ''}`}
            onClick={() => setActiveView('practice')}
          >
            Practice
          </button>
          <button
            type="button"
            className={`menu-link ${activeView === 'account' ? 'active' : ''}`}
            onClick={() => setActiveView('account')}
          >
            Account
          </button>
        </nav>
        <div className="topbar-trailing">
          <button
            type="button"
            className="topbar-capital topbar-capital-dual"
            onClick={() => setCapitalRiskOpen(true)}
            title="Open Swing & Intraday capital"
          >
            <span className="topbar-capital-line">
              <span>Swing</span>
              <strong>
                {new Intl.NumberFormat('en-IN', {
                  style: 'currency',
                  currency: 'INR',
                  maximumFractionDigits: 0,
                }).format(Number(swingEquity) || 0)}
              </strong>
            </span>
            <span className="topbar-capital-line">
              <span>Intraday</span>
              <strong>
                {new Intl.NumberFormat('en-IN', {
                  style: 'currency',
                  currency: 'INR',
                  maximumFractionDigits: 0,
                }).format(Number(intradayEquity) || 0)}
              </strong>
            </span>
          </button>
          <div className="mode-toggle-wrap">
            <div className="mode-toggle" role="group" aria-label="Guided or Pro">
              <button
                type="button"
                className={guidedMode ? 'active' : ''}
                onClick={() => persistGuidedMode(true)}
              >
                Guided
              </button>
              <button
                type="button"
                className={!guidedMode ? 'active' : ''}
                onClick={() => persistGuidedMode(false)}
              >
                Pro
              </button>
            </div>
            <button
              type="button"
              className="mode-compare-btn"
              onClick={() => setGuidedProOpen(true)}
              title="Guided vs Pro"
              aria-label="Compare Guided and Pro modes"
            >
              ?
            </button>
          </div>
          <button
            type="button"
            className="theme-toggle"
            onClick={() =>
              setTheme((current) =>
                current === 'light' ? 'dark' : current === 'dark' ? 'system' : 'light',
              )
            }
            aria-label={`Theme: ${theme}. Click to change.`}
            title={`Theme: ${theme}`}
          >
            <span className="theme-toggle-icon" aria-hidden="true">
              {resolveTheme(theme) === 'dark' ? '?' : '?'}
            </span>
          </button>
        </div>
      </header>

      <DataReadinessBanner
        status={productStatus}
        formatDateTime={formatDateTime}
        onRefresh={refreshProductStatus}
      />

      {entryAlerts.length > 0 && (
        <div className="start-trade-alert" role="alert" aria-live="assertive">
          <div className="start-trade-alert-head">
            <strong>Start real trade now</strong>
            <span>Buy/sell price reached on practice watch � place your broker order if you choose to trade.</span>
            <button type="button" className="secondary-button" onClick={dismissAllEntryAlerts}>
              Dismiss all
            </button>
          </div>
          <div className="start-trade-alert-list">
            {entryAlerts.map((trade) => (
              <div key={`alert-${trade.id}`} className="start-trade-alert-card">
                <div className="start-trade-alert-main">
                  <button
                    type="button"
                    className="symbol-link"
                    onClick={() => openStockDetail(trade.symbol)}
                  >
                    {trade.symbol}
                  </button>
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

      {showPracticeStrip && !scanFocusOpen && (
        <div
          className={`live-practice-strip${openPaperTrades.length > 0 ? ' is-live' : ' is-watching'}`}
          aria-live="polite"
        >
          <div className="live-practice-strip-label">
            <span className="live-practice-badge" aria-hidden="true">
              <span className="live-practice-badge-dot" />
              {openPaperTrades.length > 0 ? 'LIVE' : 'WATCHING'}
            </span>
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
                setActiveView('practice')
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
                    <button
                      type="button"
                      className="symbol-link"
                      onClick={() => openStockDetail(trade.symbol)}
                    >
                      {trade.symbol}
                    </button>
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
                          : `~${outlook.estimated_trading_days}d � ${formatDateTime(outlook.estimated_reach_at)}`}
                      </span>
                    ) : (
                      <span className="live-practice-eta">Est. profit: analyzing�</span>
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
                  <button type="button" className="symbol-link" onClick={() => openStockDetail(trade.symbol)}>{trade.symbol}</button>
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

      {activeView === 'home' && (
        <HomeHub
          onOpenSwing={() => setActiveView('scan')}
          onOpenIntraday={() => setActiveView('intraday')}
          onOpenResearch={() => setActiveView('research')}
          onOpenBrief={() => setActiveView('brief')}
          onOpenCompare={() => setActiveView('compare')}
          guidedMode={guidedMode}
          dataLive={Boolean(productStatus?.live_ready)}
          lastCandleTime={
            productStatus?.last_candle_time
              ? formatDateTime(productStatus.last_candle_time)
              : null
          }
        />
      )}

      {activeView === 'brief' && (
        <BriefCenter
          baseUrl={baseUrl}
          formatPrice={formatPrice}
          onOpenSwing={() => setActiveView('scan')}
        />
      )}

      {activeView === 'compare' && (
        <CompareNamesDesk
          baseUrl={baseUrl}
          formatPrice={formatPrice}
          onOpenResearch={(sym) => {
            setSelectedSymbol(sym)
            setActiveView('research')
          }}
        />
      )}

      {activeView === 'scan' && (
      <section
        className={`panel scan-panel find-setups-panel ${guidedMode ? 'guided' : 'pro'}${
          scanFocusOpen ? ' is-inspecting' : ''
        }`}
      >
        {!scanFocusOpen ? (
          <header className="header-block find-setups-header">
            <div className="swing-screen-head">
              <div>
                <p className="eyebrow">Swing</p>
                <h1>Find setups</h1>
                <p className="header-copy">
                  Ranked breakout-retest ideas on your filtered NSE universe. Engine owns Entry / Stop / Target.
                </p>
              </div>
              <nav className="swing-subnav" aria-label="Swing screens">
                <button type="button" className="swing-subnav-link active" disabled>
                  Find setups
                </button>
                <button
                  type="button"
                  className="swing-subnav-link"
                  onClick={() => {
                    setActiveView('history')
                    void refreshScanHistory()
                  }}
                >
                  Scan history
                </button>
              </nav>
            </div>
          </header>
        ) : null}

        {!scanFocusOpen ? (
        <FindSetupsCriteriaBar
          universeLabel={SCAN_UNIVERSES.find((item) => item.value === scanUniverse)?.label ?? scanUniverse}
          filterSummary={
            scanFilters.asset_class === 'ALL'
              ? 'Stocks + ETFs'
              : scanFilters.asset_class === 'STOCK'
                ? 'Stocks'
                : 'ETFs'
          }
          filterCount={countActiveFilters(scanFilters)}
          riskPercent={riskPercent}
          onRiskChange={(value) => {
            setRiskPercent(value)
            try {
              localStorage.setItem(
                RISK_STORAGE_KEY,
                JSON.stringify({
                  swingEquity,
                  intradayEquity,
                  riskPercent: value,
                  equity: swingEquity,
                }),
              )
            } catch {
              /* ignore */
            }
          }}
          onOpenUniverse={() => setUniverseOpen(true)}
          onOpenFilters={() => setFiltersOpen(true)}
          onFindSetups={() => void handleScan()}
          loading={scanLoading}
          progress={scanProgress}
          collapsed={Boolean(scanResult && scanCriteriaCollapsed)}
          onToggleCollapsed={() => setScanCriteriaCollapsed((c) => !c)}
          showCollapse={Boolean(scanResult)}
          advanced={
            <details className="find-advanced">
              <summary>More criteria (dates, capital, practice)</summary>
              <div className="find-advanced-body">
                <div className="universe-trigger-actions" style={{ marginBottom: '0.75rem' }}>
                  <button type="button" className="secondary-button" onClick={() => setPresetsOpen(true)}>
                    Presets
                  </button>
                  <button type="button" className="secondary-button" onClick={() => setCoverageOpen(true)}>
                    Coverage
                  </button>
                  <button type="button" className="link-button" onClick={() => setGuidedProOpen(true)}>
                    Guided vs Pro
                  </button>
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
                    <label htmlFor="scan-equity">Swing capital (₹)</label>
                    <input
                      id="scan-equity"
                      type="number"
                      min="0"
                      step="0.01"
                      value={swingEquity}
                      onChange={(event) => setSwingEquity(event.target.value)}
                    />
                  </div>
                  <div className="field-group">
                    <label htmlFor="scan-top-n">Top ideas to highlight</label>
                    <select id="scan-top-n" value={topN} onChange={(event) => setTopN(event.target.value)}>
                      <option value="3">Top 3</option>
                      <option value="5">Top 5</option>
                      <option value="10">Top 10</option>
                    </select>
                  </div>
                </div>
                <div className="field-row two-col">
                  <div className="field-group">
                    <label htmlFor="scan-min-score">Min strategy confidence %</label>
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
                  <div className="field-group paper-opt-in">
                    <label className="checkbox-label" htmlFor="scan-paper-enabled">
                      <input
                        id="scan-paper-enabled"
                        type="checkbox"
                        checked={paperTradingEnabled}
                        onChange={(event) => setPaperEnabled(event.target.checked)}
                      />
                      <span>Practice trades (optional) � fake money only.</span>
                    </label>
                  </div>
                </div>
              </div>
            </details>
          }
        />
        ) : null}

        {scanError && !scanFocusOpen && <div className="status error">{scanError}</div>}

        {scanResult && chartEvidenceOpen && selectedOpportunity ? (
          <ChartEvidenceDesk
            opportunity={selectedOpportunity}
            chartCandles={chartCandles}
            formatPrice={formatPrice}
            formatNumber={formatNumber}
            formatVolume={formatVolume}
            formatDateTime={formatDateTime}
            formatBarRef={formatBarRef}
            coveragePct={(() => {
              const after = Number(scanResult.filter_coverage?.after_filters ?? scanResult.symbols_scanned)
              if (!after) return null
              return Math.max(0, Math.min(100, (100 * Number(scanResult.symbols_scanned || 0)) / after))
            })()}
            dataAsOf={scanResult.last_candle_time ?? productStatus?.last_candle_time ?? null}
            onBack={() => setChartEvidenceOpen(false)}
            onClose={() => {
              setChartEvidenceOpen(false)
              setInspectPlanOpen(false)
            }}
            onRefresh={() => void handleScan()}
            refreshing={scanLoading}
            onOpenResearch={() => {
              setChartEvidenceOpen(false)
              setInspectPlanOpen(false)
              if (selectedOpportunity?.symbol) {
                setSelectedSymbol(selectedOpportunity.symbol)
                setSelectedKind('eligible')
              }
              setActiveView('research')
            }}
          />
        ) : null}

        {scanResult && inspectPlanOpen && !chartEvidenceOpen && selectedOpportunity ? (
          <InspectPlanDesk
            opportunity={selectedOpportunity}
            baseUrl={baseUrl}
            chartCandles={chartCandles}
            deductionSteps={inspectDeductionSteps}
            formatPrice={formatPrice}
            formatRatio={formatRatio}
            formatDateTime={formatDateTime}
            coveragePct={(() => {
              const after = Number(scanResult.filter_coverage?.after_filters ?? scanResult.symbols_scanned)
              if (!after) return null
              return Math.max(0, Math.min(100, (100 * Number(scanResult.symbols_scanned || 0)) / after))
            })()}
            dataAsOf={scanResult.last_candle_time ?? productStatus?.last_candle_time ?? null}
            onClose={() => {
              setInspectPlanOpen(false)
              setChartEvidenceOpen(false)
            }}
            onRefresh={() => void handleScan()}
            refreshing={scanLoading}
            onOpenResearch={() => {
              setInspectPlanOpen(false)
              setChartEvidenceOpen(false)
              setSelectedSymbol(selectedOpportunity.symbol)
              setSelectedKind('eligible')
              setActiveView('research')
            }}
            onOpenChartEvidence={() => setChartEvidenceOpen(true)}
            siblings={showAllOpportunities ? filteredOpportunities : visibleOpportunities}
            onSelectSibling={(symbol) => {
              setSelectedSymbol(symbol)
              setSelectedKind('eligible')
            }}
          />
        ) : null}

        {scanResult && !scanFocusOpen ? (
          <FindSetupsResultsLayout
            scanResult={scanResult}
            topIdeas={topReadyIdeas}
            rows={showAllOpportunities ? filteredOpportunities : visibleOpportunities}
            selectedSymbol={selectedSymbol}
            onSelect={(symbol) => {
              setSelectedSymbol(symbol)
              setSelectedKind('eligible')
            }}
            onOpenDetail={(symbol) => {
              setSelectedSymbol(symbol)
              setSelectedKind('eligible')
              setInspectPlanOpen(true)
            }}
            onViewAll={() => setShowAllOpportunities((v) => !v)}
            showAll={showAllOpportunities}
            formatPrice={formatPrice}
            sortLabel={resultControls.sortBy === 'confidence' ? 'confidence' : resultControls.sortBy}
            onSortChange={(value) => {
              const sortBy = (value === 'Score' || value === 'confidence' ? 'confidence' : value) as typeof resultControls.sortBy
              setResultControls((current) => ({
                ...current,
                sortBy: sortBy === 'confidence' || sortBy === 'rank' || sortBy === 'rr' || sortBy === 'symbol' ? sortBy : 'confidence',
                sortDir: sortBy === 'rank' || sortBy === 'symbol' ? 'asc' : 'desc',
              }))
            }}
            coveragePct={(() => {
              const after = Number(scanResult.filter_coverage?.after_filters ?? scanResult.symbols_scanned)
              if (!after) return null
              return Math.max(0, Math.min(100, (100 * Number(scanResult.symbols_scanned || 0)) / after))
            })()}
            dataAsOf={scanResult.last_candle_time ?? productStatus?.last_candle_time ?? null}
            formatDateTime={formatDateTime}
            onRefresh={() => void handleScan()}
            refreshing={scanLoading}
            onExportCsv={() => downloadEligibleCsv(scanResult, filteredOpportunities)}
            onOpenCoverage={() => setCoverageOpen(true)}
            autoRefresh={{
              enabled: autoRefreshActive,
              onEnabledChange: setAutoRefreshActive,
              intervalSec: refreshInterval,
              onIntervalChange: (next) => {
                setRefreshInterval(next)
                setSwingRefreshSec(next)
                setAutoRefreshActive(true)
              },
              secondsLeft: autoRefreshSecondsLeft,
              paused: autoRefreshPaused,
              pauseReason: autoRefreshPauseReason,
              refreshing: scanLoading,
            }}
          />
        ) : null}

        {scanResult && !scanFocusOpen && (
          <>
            {(scanResult.forming?.length ?? 0) > 0 || (scanResult.forming_count ?? 0) > 0 ? (
              <FormingWatchlistDesk
                scanResult={scanResult}
                rows={filteredForming}
                selectedSymbol={selectedKind === 'forming' ? selectedSymbol : null}
                onSelect={(symbol) => {
                  setSelectedSymbol(symbol)
                  setSelectedKind('forming')
                }}
                onOpenDetail={(symbol) => openStockDetail(symbol, 'forming')}
                formingControls={formingControls}
                onFormingControlsChange={setFormingControls}
                onResetFilters={() => setFormingControls(DEFAULT_FORMING_CONTROLS)}
                formatPrice={formatPrice}
                formatNumber={formatNumber}
                formatPercent={formatPercent}
                formatDateTime={formatDateTime}
                coveragePct={(() => {
                  const after = Number(scanResult.filter_coverage?.after_filters ?? scanResult.symbols_scanned)
                  if (!after) return null
                  return Math.max(0, Math.min(100, (100 * Number(scanResult.symbols_scanned || 0)) / after))
                })()}
                dataAsOf={scanResult.last_candle_time ?? productStatus?.last_candle_time ?? null}
                onRefresh={() => void handleScan()}
                refreshing={scanLoading}
              />
            ) : null}

            {paperNotice ? <div className="status ok">{paperNotice}</div> : null}
            {paperError ? <div className="status error">{paperError}</div> : null}
            <PracticeFromScanDesk
              scanResult={scanResult}
              opportunities={filteredOpportunities}
              paperTrades={paperBook?.trades ?? []}
              paperEnabled={paperTradingEnabled}
              onEnablePaper={() => {
                setPaperEnabled(true)
                void refreshPaperBook()
                void tickPaperBook()
              }}
              baseUrl={baseUrl}
              chartCandles={chartCandles}
              focusSymbol={selectedKind === 'eligible' ? selectedSymbol : null}
              onFocusSymbol={(symbol) => {
                setSelectedSymbol(symbol)
                setSelectedKind('eligible')
              }}
              formatPrice={formatPrice}
              formatDateTime={formatDateTime}
              coveragePct={(() => {
                const after = Number(scanResult.filter_coverage?.after_filters ?? scanResult.symbols_scanned)
                if (!after) return null
                return Math.max(0, Math.min(100, (100 * Number(scanResult.symbols_scanned || 0)) / after))
              })()}
              dataAsOf={scanResult.last_candle_time ?? productStatus?.last_candle_time ?? null}
              onRefresh={() => void handleScan()}
              refreshing={scanLoading}
              onArmed={(message) => {
                setPaperEnabled(true)
                setPaperNotice(message)
                setPaperError('')
                void refreshPaperBook()
                void tickPaperBook()
              }}
              onOpenBook={() => {
                setActiveView('practice')
                void refreshPaperBook()
                void tickPaperBook()
              }}
              onTick={() => void tickPaperBook()}
              ticking={false}
            />
          </>
        )}
      </section>
      )}

      {activeView === 'history' && (
        <section className={`panel scan-panel scan-history-panel ${guidedMode ? 'guided' : 'pro'}`}>
          <header className="header-block find-setups-header">
            <div className="swing-screen-head">
              <div>
                <p className="eyebrow">Swing</p>
                <h1>Scan history</h1>
                <p className="header-copy">
                  Reopen a past run into Find setups, or export eligible setups as CSV.
                </p>
              </div>
              <nav className="swing-subnav" aria-label="Swing screens">
                <button type="button" className="swing-subnav-link" onClick={() => setActiveView('scan')}>
                  Find setups
                </button>
                <button type="button" className="swing-subnav-link active" disabled>
                  Scan history
                </button>
              </nav>
            </div>
          </header>
          <ScanHistoryDesk
            runs={scanHistory}
            selectedId={historySelectedId}
            onSelect={setHistorySelectedId}
            onOpen={(id) => void openScanHistoryRun(id)}
            onExportCsv={(id) => exportScanHistoryCsv(id)}
            busyId={historyBusyId}
            error={historyError}
            coveragePct={(() => {
              const selected = scanHistory.find((run) => run.id === historySelectedId) ?? scanHistory[0]
              return selected ? scanCoveragePct(selected) : null
            })()}
            dataAsOf={productStatus?.last_candle_time ?? null}
            onRefresh={() => void refreshScanHistory()}
            refreshing={historyRefreshing}
            formatDateTime={formatDateTime}
          />
        </section>
      )}

      {activeView === 'intraday' && (
        <IntradayDesk
          baseUrl={baseUrl}
          accountEquity={intradayEquity}
          onEquityChange={setIntradayEquity}
          preferredBoardRefreshSec={Number(intradayRefreshSec) || 30}
        />
      )}

      {detailDrawerOpen && selectedSymbol && !scanFocusOpen && (
        <StockDetailDrawer
          baseUrl={baseUrl}
          symbol={selectedSymbol}
          scanStart={scanStart}
          scanEnd={scanEnd}
          chartCandles={chartCandles}
          opportunity={selectedOpportunity}
          forming={selectedForming}
          confirmationMatchesScanEnd={(opportunity) =>
            confirmationMatchesScanEnd(opportunity as Opportunity)
          }
          onClose={() => setDetailDrawerOpen(false)}
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
        <ResearchDesk
          baseUrl={baseUrl}
          initialSymbol={selectedSymbol}
          accountEquity={swingEquity}
          riskPercent={riskPercent}
          formatPrice={formatPrice}
          formatNumber={formatNumber}
          formatPercent={formatPercent}
          formatVolume={formatVolume}
          formatDateTime={formatDateTime}
          valueClass={valueClass}
          onOpenEligibility={() => setActiveView('intraday')}
          onOpenFilters={() => {
            setActiveView('scan')
            setFiltersOpen(true)
          }}
        />
      )}

      {activeView === 'practice' && (
        <PracticeBook
          baseUrl={baseUrl}
          swingEquity={swingEquity}
          intradayEquity={intradayEquity}
          paperTradingEnabled={paperTradingEnabled}
          onEnablePaper={() => {
            setPaperEnabled(true)
            void refreshPaperBook()
            void tickPaperBook()
          }}
          onTradesChanged={refreshPaperBook}
          onOpenSwing={() => setActiveView('scan')}
          onOpenIntraday={() => setActiveView('intraday')}
        />
      )}

      {activeView === 'account' && (
        <AccountShell
          baseUrl={baseUrl}
          theme={theme}
          onThemeChange={setTheme}
          swingEquity={swingEquity}
          intradayEquity={intradayEquity}
          riskPercent={riskPercent}
          onSwingEquityChange={setSwingEquity}
          onIntradayEquityChange={setIntradayEquity}
          onRiskChange={setRiskPercent}
          paperTradingEnabled={paperTradingEnabled}
          onPaperEnabledChange={setPaperEnabled}
          onOpenCapital={() => setCapitalRiskOpen(true)}
          swingRefreshSec={swingRefreshSec}
          intradayRefreshSec={intradayRefreshSec}
          practiceTickMode={practiceTickMode}
          initialTab={accountInitialTab}
          onSaveRefresh={({ swingRefreshSec: swing, intradayRefreshSec: intra, practiceTickMode: practice }) => {
            setSwingRefreshSec(swing)
            setIntradayRefreshSec(intra)
            setPracticeTickMode(practice)
            setRefreshInterval(swing)
          }}
        />
      )}

      <CapitalRisk
        open={capitalRiskOpen}
        onClose={() => setCapitalRiskOpen(false)}
        swingEquity={swingEquity}
        intradayEquity={intradayEquity}
        riskPercent={riskPercent}
        onSwingEquityChange={setSwingEquity}
        onIntradayEquityChange={setIntradayEquity}
        onRiskChange={setRiskPercent}
        dataLive={Boolean(productStatus?.live_ready)}
        lastCandleTime={
          productStatus?.last_candle_time
            ? formatDateTime(productStatus.last_candle_time)
            : null
        }
      />

      <UniversePicker
        open={universeOpen}
        onClose={() => setUniverseOpen(false)}
        baseUrl={baseUrl}
        value={scanUniverse}
        onChange={(next) => {
          setScanUniverse(next)
          try {
            localStorage.setItem(UNIVERSE_STORAGE_KEY, next)
          } catch {
            /* ignore */
          }
          setScanFilters((prev) => {
            const updated = { ...prev, asset_class: assetClassForUniverse(next) }
            persistScanFilters(updated)
            return updated
          })
        }}
      />

      <FilterBuilder
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        baseUrl={baseUrl}
        value={scanFilters}
        onChange={(next) => {
          setScanFilters(next)
          persistScanFilters(next)
        }}
        universe={scanUniverse}
        onUniverseChange={(next) => {
          const u = next as ScanUniverse
          setScanUniverse(u)
          try {
            localStorage.setItem(UNIVERSE_STORAGE_KEY, u)
          } catch {
            /* ignore */
          }
        }}
        universeOptions={SCAN_UNIVERSES}
        strategyLabel="BreakoutRetest"
        onManagePresets={() => {
          setFiltersOpen(false)
          setPresetsOpen(true)
        }}
      />

      <FilterPresets
        open={presetsOpen}
        onClose={() => setPresetsOpen(false)}
        baseUrl={baseUrl}
        universe={scanUniverse}
        value={scanFilters}
        onChange={(next) => {
          setScanFilters(next)
          persistScanFilters(next)
        }}
        onEdit={() => {
          setPresetsOpen(false)
          setFiltersOpen(true)
        }}
      />

      <CoverageDrawer
        open={coverageOpen}
        onClose={() => setCoverageOpen(false)}
        baseUrl={baseUrl}
        universe={scanUniverse}
        filters={scanFilters}
        scanIssues={scanResult?.issues ?? null}
        dataAsOf={productStatus?.last_candle_time ?? scanResult?.last_candle_time ?? null}
        formatDateTime={formatDateTime}
      />

      <GuidedProMode
        open={guidedProOpen}
        onClose={() => setGuidedProOpen(false)}
        guidedMode={guidedMode}
        onSelectGuided={() => {
          persistGuidedMode(true)
          setGuidedProOpen(false)
        }}
        onSelectPro={() => {
          persistGuidedMode(false)
          setGuidedProOpen(false)
        }}
        onFindSetups={() => {
          persistGuidedMode(true)
          setGuidedProOpen(false)
          setActiveView('scan')
          setShowHowItWorks(true)
        }}
        onShowHowItWorks={() => {
          persistGuidedMode(true)
          setGuidedProOpen(false)
          setActiveView('scan')
          setShowHowItWorks(true)
        }}
        dataLive={Boolean(productStatus?.live_ready)}
        lastCandleTime={
          productStatus?.last_candle_time
            ? formatDateTime(productStatus.last_candle_time)
            : null
        }
      />

      <p className="disclaimer">
        Educational decision support only. TradePilot does not place broker orders and is not investment advice.
        Live prices and candles require a configured Upstox connection.
      </p>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
