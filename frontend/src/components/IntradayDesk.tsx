import { useEffect, useMemo, useRef, useState } from 'react'
import { PlanDeductionPanel } from './PlanDeductionPanel'
import { OrbChart } from './OrbChart'
import { FilterBuilder, DEFAULT_FILTERS, filtersToPayload, type UniverseFilterState } from './FilterBuilder'
import { CoverageDrawer } from './CoverageDrawer'
import {
  ensure1mActiveSet,
  fetchMorningBoard,
  getIntradaySession,
  getIntradaySessionChart,
  getPracticeDivergence,
  listIntradayPractice,
  runIntradaySession,
  runMorningIntradaySession,
  seedIntradayPractice,
  tickIntradayPractice,
  type IntradayChartResponse,
  type IntradayClosedTrade,
  type IntradayFill,
  type IntradayPracticeTrade,
  type IntradayRankedRow,
  type IntradaySessionResponse,
  type IntradaySymbolResult,
  type IntradayUniverse,
  type MorningBoardResponse,
} from '../intraday/api'
import { buildOrbDeductionSteps } from '../intraday/planDeduction'
import {
  directionLabel,
  exitReasonLabel,
  orbPaperClaim,
  orbReasonHint,
  orbReasonLabel,
  ORB_V1_RULES,
} from '../terminology'

type Props = {
  baseUrl: string
  accountEquity: string
  onEquityChange?: (value: string) => void
}

type OutcomeFilter = 'ALL' | 'TRADED' | 'ARMED' | 'BLOCKED' | 'SKIPPED'

const DEMO_SAMPLE = 'ORBDEMO, ADANIENT, ADANIPORTS, APOLLOHOSP, ASIANPAINT'

const UNIVERSE_OPTIONS: { value: IntradayUniverse; label: string }[] = [
  { value: 'DEMO_SAMPLE', label: 'Demo sample' },
  { value: 'NIFTY_50', label: 'Nifty 50' },
  { value: 'NIFTY_100', label: 'Nifty 100' },
  { value: 'NIFTY_500', label: 'Nifty 500' },
  { value: 'NSE_ETF', label: 'NSE ETFs' },
  { value: 'NSE_CASH', label: 'NSE cash' },
  { value: 'NSE_ALL', label: 'NSE all' },
  { value: 'CUSTOM', label: 'Custom' },
]

function formatInr(value: string | number | null | undefined): string {
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

function reasonTone(reason: string): string {
  if (reason === 'TRADED') return 'intraday-reason traded'
  if (
    reason.includes('LOCK') ||
    reason === 'RISK_INVALID' ||
    reason === 'ORDER_REJECTED' ||
    reason === 'PORTFOLIO_RISK_LIMIT' ||
    reason === 'SHORT_NOT_PERMITTED' ||
    reason === 'SURVEILLANCE_BLOCKED' ||
    reason === 'PRICE_BAND_RISK' ||
    reason === 'CORPORATE_ACTION_BLOCK'
  ) {
    return 'intraday-reason blocked'
  }
  if (reason === 'RANKED_ARMED' || reason === 'BREAKOUT_NOT_TRIGGERED') return 'intraday-reason armed'
  return 'intraday-reason muted'
}

function outcomeBucket(reason: string): Exclude<OutcomeFilter, 'ALL'> {
  if (reason === 'TRADED') return 'TRADED'
  if (reason === 'RANKED_ARMED' || reason === 'BREAKOUT_NOT_TRIGGERED') return 'ARMED'
  if (
    reason.includes('LOCK') ||
    reason === 'RISK_INVALID' ||
    reason === 'ORDER_REJECTED' ||
    reason === 'PORTFOLIO_RISK_LIMIT' ||
    reason === 'SHORT_NOT_PERMITTED' ||
    reason === 'SURVEILLANCE_BLOCKED' ||
    reason === 'PRICE_BAND_RISK' ||
    reason === 'CORPORATE_ACTION_BLOCK'
  ) {
    return 'BLOCKED'
  }
  return 'SKIPPED'
}

function csvEscape(value: string | number | null | undefined): string {
  const text = value == null ? '' : String(value)
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

function downloadSessionCsv(session: IntradaySessionResponse) {
  const lines = [
    ['section', 'symbol', 'rank', 'side', 'rvol5', 'outcome', 'detail', 'entry', 'stop', 'qty', 'exit', 'exit_reason', 'pnl'].join(
      ',',
    ),
  ]
  for (const row of session.symbol_results) {
    lines.push(
      [
        'ledger',
        row.symbol,
        row.rank ?? '',
        row.direction ?? '',
        row.rvol5 ?? '',
        row.reason,
        row.detail ?? '',
        '',
        '',
        '',
        '',
        '',
        '',
      ]
        .map(csvEscape)
        .join(','),
    )
  }
  for (const fill of session.fills) {
    lines.push(
      [
        'fill',
        fill.symbol,
        fill.rank,
        fill.direction,
        '',
        'TRADED',
        fill.trigger_bar_open,
        fill.entry,
        fill.stop,
        fill.quantity,
        '',
        '',
        '',
      ]
        .map(csvEscape)
        .join(','),
    )
  }
  for (const trade of session.closed_trades) {
    lines.push(
      [
        'closed',
        trade.symbol,
        '',
        trade.direction,
        '',
        trade.exit_reason,
        trade.exit_time,
        trade.entry,
        trade.stop ?? '',
        trade.quantity ?? '',
        trade.exit,
        trade.exit_reason,
        trade.pnl,
      ]
        .map(csvEscape)
        .join(','),
    )
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `tradepilot-intraday-${session.session_date}-${session.id.slice(0, 8)}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

function MorningRankTable({
  title,
  rows,
  empty,
  onExplain,
}: {
  title: string
  rows: IntradayRankedRow[]
  empty: string
  onExplain?: (symbol: string) => void
}) {
  return (
    <div className="confirmed-box intraday-table-box">
      <div className="table-toolbar">
        <div>
          <h3>{title}</h3>
          <p className="field-hint">
            Showing {rows.length} ranked {title.toLowerCase()}. Rank is RVOL order for this session.
          </p>
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="empty-state">
          <strong>No rows</strong>
          <span>{empty}</span>
        </div>
      ) : (
        <div className="table-wrap scan-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Stock</th>
                <th>Trade type</th>
                <th>RVOL5</th>
                <th>OR high</th>
                <th>OR low</th>
                <th>Status</th>
                {onExplain ? <th>How decided</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isShort = row.direction === 'SHORT'
                return (
                  <tr key={`${row.asset_class}-${row.symbol}`}>
                    <td className="num-cell">
                      <span className="rank-badge">#{row.rank ?? '—'}</span>
                    </td>
                    <td className="symbol-cell">
                      {onExplain ? (
                        <button type="button" className="symbol-link" onClick={() => onExplain(row.symbol)}>
                          {row.symbol}
                        </button>
                      ) : (
                        <span className="symbol-link">{row.symbol}</span>
                      )}
                    </td>
                    <td>
                      {row.direction ? (
                        <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                          {directionLabel(row.direction)}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="num-cell">
                      {row.rvol5 != null ? Number(row.rvol5).toFixed(2) : '—'}
                    </td>
                    <td className="num-cell">{row.or_high ? formatInr(row.or_high) : '—'}</td>
                    <td className="num-cell">{row.or_low ? formatInr(row.or_low) : '—'}</td>
                    <td>
                      <span
                        className={reasonTone(row.status === 'RANKED' ? 'RANKED_ARMED' : row.status || 'NO_SETUP')}
                      >
                        {row.status || '—'}
                      </span>
                    </td>
                    {onExplain ? (
                      <td className="deduction-cell">
                        <button
                          type="button"
                          className="ghost-btn deduction-toggle"
                          onClick={() => onExplain(row.symbol)}
                        >
                          How decided
                        </button>
                      </td>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function IntradayDesk({ baseUrl, accountEquity, onEquityChange }: Props) {
  const [universe, setUniverse] = useState<IntradayUniverse>('DEMO_SAMPLE')
  const [boardFilters, setBoardFilters] = useState<UniverseFilterState>(DEFAULT_FILTERS)
  const [symbolsText, setSymbolsText] = useState(DEMO_SAMPLE)
  const [sessionDate, setSessionDate] = useState('2026-09-07')
  const [source, setSource] = useState<'demo' | 'persisted'>('demo')
  const [showHow, setShowHow] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [coverageOpen, setCoverageOpen] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>('ALL')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [session, setSession] = useState<IntradaySessionResponse | null>(null)
  const [explainSymbol, setExplainSymbol] = useState<string | null>(null)
  const [chart, setChart] = useState<IntradayChartResponse | null>(null)
  const [chartError, setChartError] = useState('')
  const [chartLoading, setChartLoading] = useState(false)
  const [practice, setPractice] = useState<IntradayPracticeTrade[]>([])
  const [practiceClaim, setPracticeClaim] = useState('')
  const [practiceBusy, setPracticeBusy] = useState(false)
  const [chartTf, setChartTf] = useState<'1m' | '5m'>('1m')
  const [divergence, setDivergence] = useState<Awaited<ReturnType<typeof getPracticeDivergence>> | null>(null)
  const [morningBoard, setMorningBoard] = useState<MorningBoardResponse | null>(null)
  const [boardLoading, setBoardLoading] = useState(false)
  const [boardAutoRefresh, setBoardAutoRefresh] = useState(true)
  const [ledgerVisibleCount, setLedgerVisibleCount] = useState(10)
  const [ledgerOpen, setLedgerOpen] = useState(true)
  const [fillsOpen, setFillsOpen] = useState(true)
  const [finishedOpen, setFinishedOpen] = useState(true)
  const boardBusyRef = useRef(false)

  useEffect(() => {
    if (!session?.id) {
      setPractice([])
      setPracticeClaim('')
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const next = await listIntradayPractice(baseUrl, session.id)
        if (!cancelled) {
          setPractice(next.trades)
          setPracticeClaim(next.claim)
        }
      } catch {
        if (!cancelled) setPractice([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [baseUrl, session?.id])

  async function handleSeedPractice() {
    if (!session?.id) return
    setPracticeBusy(true)
    setError('')
    try {
      const result = await seedIntradayPractice(baseUrl, session.id)
      setPracticeClaim(result.claim)
      const listed = await listIntradayPractice(baseUrl, session.id)
      setPractice(listed.trades)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Practice seed failed')
    } finally {
      setPracticeBusy(false)
    }
  }

  async function handlePracticeTick(forceEod = false, liveQuotes = true) {
    if (!session?.id) return
    setPracticeBusy(true)
    setError('')
    try {
      const marks: Record<string, string> | undefined = liveQuotes
        ? undefined
        : Object.fromEntries(
            practice
              .filter((t) => t.status === 'OPEN')
              .map((trade) => {
                const closed = session.closed_trades.find((t) => t.symbol === trade.symbol)
                return [trade.symbol, closed?.exit ?? trade.last_mark_price ?? trade.entry_price]
              }),
          )
      await tickIntradayPractice(baseUrl, session.id, {
        marks,
        force_eod: forceEod,
        use_live_quotes: liveQuotes && !forceEod,
      })
      const listed = await listIntradayPractice(baseUrl, session.id)
      setPractice(listed.trades)
      setPracticeClaim(listed.claim)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Practice tick failed')
    } finally {
      setPracticeBusy(false)
    }
  }

  async function handleDivergence() {
    if (!session?.id) return
    setPracticeBusy(true)
    setError('')
    try {
      setDivergence(await getPracticeDivergence(baseUrl, session.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Divergence check failed')
    } finally {
      setPracticeBusy(false)
    }
  }

  useEffect(() => {
    if (!session?.id || !explainSymbol) {
      setChart(null)
      setChartError('')
      return
    }
    let cancelled = false
    setChartLoading(true)
    setChartError('')
    void (async () => {
      try {
        const next = await getIntradaySessionChart(baseUrl, session.id, explainSymbol, chartTf)
        if (!cancelled) setChart(next)
      } catch (err) {
        if (!cancelled) {
          setChart(null)
          setChartError(err instanceof Error ? err.message : 'Chart unavailable')
        }
      } finally {
        if (!cancelled) setChartLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [baseUrl, session?.id, explainSymbol, chartTf])

  async function loadMorningBoard(opts?: { quiet?: boolean }) {
    if (boardBusyRef.current) return
    boardBusyRef.current = true
    if (!opts?.quiet) {
      setBoardLoading(true)
      setError('')
    }
    try {
      const customSymbols =
        universe === 'CUSTOM'
          ? symbolsText
              .split(/[\s,]+/)
              .map((s) => s.trim().toUpperCase())
              .filter(Boolean)
          : universe === 'DEMO_SAMPLE'
            ? DEMO_SAMPLE.split(/[\s,]+/).map((s) => s.trim())
            : undefined
      const board = await fetchMorningBoard(baseUrl, {
        session_date: sessionDate || null,
        source,
        equity: accountEquity || '1000000',
        universe: universe === 'CUSTOM' ? 'NSE_ALL' : universe,
        symbols: customSymbols,
        filters: filtersToPayload(boardFilters),
      })
      setMorningBoard(board)
    } catch (err) {
      if (!opts?.quiet) {
        setError(err instanceof Error ? err.message : 'Morning board failed')
      }
    } finally {
      boardBusyRef.current = false
      if (!opts?.quiet) setBoardLoading(false)
    }
  }

  useEffect(() => {
    if (!boardAutoRefresh || !morningBoard) return
    const ms = Math.max(10, morningBoard.auto_refresh_seconds || 30) * 1000
    const timer = window.setInterval(() => {
      void loadMorningBoard({ quiet: true })
    }, ms)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh cadence from board; reload uses latest closures
  }, [boardAutoRefresh, morningBoard?.auto_refresh_seconds, sessionDate, source, baseUrl, accountEquity, universe, boardFilters])

  async function handleMorning() {
    setLoading(true)
    setError('')
    setExplainSymbol(null)
    setDivergence(null)
    try {
      await loadMorningBoard()
      const customSymbols =
        universe === 'CUSTOM'
          ? symbolsText
              .split(/[\s,]+/)
              .map((s) => s.trim().toUpperCase())
              .filter(Boolean)
          : universe === 'DEMO_SAMPLE'
            ? DEMO_SAMPLE.split(/[\s,]+/).map((s) => s.trim())
            : null
      const result = await runMorningIntradaySession(baseUrl, {
        session_date: sessionDate || null,
        symbols: customSymbols,
        universe: universe === 'CUSTOM' ? 'NSE_ALL' : universe === 'DEMO_SAMPLE' ? 'DEMO_SAMPLE' : universe,
        equity: accountEquity || '1000000',
        source,
        seed_practice: true,
      })
      setSession({ ...result.session, id: result.session.id })
      if (result.practice) {
        setPractice(result.practice.trades)
        setPracticeClaim(result.practice.claim)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Morning run failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleRun() {
    setLoading(true)
    setError('')
    setExplainSymbol(null)
    try {
      const customSymbols =
        universe === 'CUSTOM'
          ? symbolsText
              .split(/[\s,]+/)
              .map((s) => s.trim().toUpperCase())
              .filter(Boolean)
          : universe === 'DEMO_SAMPLE'
            ? DEMO_SAMPLE.split(/[\s,]+/).map((s) => s.trim())
            : null

      const result = await runIntradaySession(baseUrl, {
        session_date: sessionDate || null,
        symbols: customSymbols,
        universe: universe === 'CUSTOM' || universe === 'DEMO_SAMPLE' ? undefined : universe,
        equity: accountEquity || '1000000',
        source,
      })
      setSession(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Session failed')
      setSession(null)
    } finally {
      setLoading(false)
    }
  }

  async function handleReload() {
    if (!session?.id) return
    setLoading(true)
    setError('')
    try {
      setSession(await getIntradaySession(baseUrl, session.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reload failed')
    } finally {
      setLoading(false)
    }
  }

  const fillsBySymbol = useMemo(() => {
    const map = new Map<string, IntradayFill>()
    for (const fill of session?.fills ?? []) map.set(fill.symbol, fill)
    return map
  }, [session])

  const closedBySymbol = useMemo(() => {
    const map = new Map<string, IntradayClosedTrade>()
    for (const trade of session?.closed_trades ?? []) map.set(trade.symbol, trade)
    return map
  }, [session])

  const counts = useMemo(() => {
    const base = { TRADED: 0, ARMED: 0, BLOCKED: 0, SKIPPED: 0, total: 0 }
    for (const row of session?.symbol_results ?? []) {
      base[outcomeBucket(row.reason)] += 1
      base.total += 1
    }
    return base
  }, [session])

  const filteredLedger = useMemo(() => {
    const rows = session?.symbol_results ?? []
    if (outcomeFilter === 'ALL') return rows
    return rows.filter((row) => outcomeBucket(row.reason) === outcomeFilter)
  }, [session, outcomeFilter])

  const visibleLedger = useMemo(
    () => filteredLedger.slice(0, ledgerVisibleCount),
    [filteredLedger, ledgerVisibleCount],
  )

  useEffect(() => {
    setLedgerVisibleCount(10)
  }, [session?.id, outcomeFilter])

  const highlightRows = useMemo(() => {
    const rows = session?.symbol_results ?? []
    return rows
      .filter((row) => row.reason === 'TRADED' || row.reason === 'RANKED_ARMED' || row.reason === 'BREAKOUT_NOT_TRIGGERED')
      .slice(0, 8)
  }, [session])

  const closedPnl = session?.closed_trades.reduce((sum, t) => sum + (Number(t.pnl) || 0), 0) ?? 0
  const riskBudget = formatInr((Number(accountEquity) * ORB_V1_RULES.riskPerTradePct) / 100)

  const explainRow: IntradaySymbolResult | null =
    session && explainSymbol
      ? (session.symbol_results.find((r) => r.symbol === explainSymbol) ?? null)
      : null
  const explainSteps =
    explainRow &&
    buildOrbDeductionSteps({
      row: explainRow,
      fill: fillsBySymbol.get(explainRow.symbol),
      closed: closedBySymbol.get(explainRow.symbol),
      accountEquity,
      formatPrice: formatInr,
    })

  const universeLabel = UNIVERSE_OPTIONS.find((opt) => opt.value === universe)?.label ?? universe
  const coverageLabel =
    session?.coverage_pct != null
      ? `${session.coverage_pct}%`
      : session
        ? `${session.coverage_eligible}/${session.coverage_total}`
        : '—'

  return (
    <section className="panel intraday-desk intraday-desk-clean">
      <header className="intraday-page-head">
        <div>
          <h1>Intraday desk · ORB opening-range breakout V1</h1>
          <p className="header-copy">
            Opening-range breakouts · safety exit · flat by {ORB_V1_RULES.flatten}. No profit target. Practice is
            fake money.
          </p>
        </div>
        <button type="button" className="link-button" onClick={() => setShowHow((v) => !v)}>
          {showHow ? 'Hide rules' : 'How it works'}
        </button>
      </header>

      {showHow && (
        <div className="intraday-how-panel">
          <ol className="intraday-how-steps">
            <li>
              <strong>OR</strong> {ORB_V1_RULES.orWindow}
            </li>
            <li>
              <strong>Rank</strong> RVOL5 · Top {ORB_V1_RULES.topN} stocks & ETFs
            </li>
            <li>
              <strong>Enter</strong> 1m breakout before {ORB_V1_RULES.entryCutoff}
            </li>
            <li>
              <strong>Size</strong> ~{ORB_V1_RULES.riskPerTradePct}% risk ({riskBudget}) · max{' '}
              {ORB_V1_RULES.maxConcurrent}
            </li>
            <li>
              <strong>Exit</strong> stop or {ORB_V1_RULES.flatten} flatten · no overnight
            </li>
          </ol>
        </div>
      )}

      <div className="intraday-toolbar">
        <label className="field">
          <span>Date</span>
          <input type="date" value={sessionDate} onChange={(e) => setSessionDate(e.target.value)} />
        </label>
        <label className="field">
          <span>Source</span>
          <select value={source} onChange={(e) => setSource(e.target.value as 'demo' | 'persisted')}>
            <option value="demo">Demo</option>
            <option value="persisted">Persisted</option>
          </select>
        </label>
        <label className="field">
          <span>Universe</span>
          <select
            value={universe}
            onChange={(e) => {
              const next = e.target.value as IntradayUniverse
              setUniverse(next)
              if (next === 'DEMO_SAMPLE') setSymbolsText(DEMO_SAMPLE)
            }}
          >
            {UNIVERSE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Capital</span>
          <input
            type="text"
            value={accountEquity}
            readOnly={!onEquityChange}
            onChange={(e) => onEquityChange?.(e.target.value)}
          />
        </label>
        {universe === 'CUSTOM' && (
          <label className="field field-grow">
            <span>Symbols</span>
            <input
              type="text"
              value={symbolsText}
              onChange={(e) => setSymbolsText(e.target.value)}
              placeholder="RELIANCE, TCS"
            />
          </label>
        )}
        <div className="intraday-toolbar-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void loadMorningBoard()}
            disabled={boardLoading || loading}
          >
            {boardLoading ? 'Screening…' : 'Morning board'}
          </button>
          <button type="button" className="primary-button" onClick={() => void handleRun()} disabled={loading}>
            {loading ? 'Running…' : 'Run session'}
          </button>
          <button type="button" className="secondary-button" onClick={() => setShowFilters((v) => !v)}>
            {showFilters ? 'Hide filters' : 'Filters'}
          </button>
          <button type="button" className="secondary-button" onClick={() => setCoverageOpen(true)}>
            Coverage
          </button>
          <button type="button" className="secondary-button" onClick={() => setShowAdvanced((v) => !v)}>
            More
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="intraday-filters-panel">
          <FilterBuilder value={boardFilters} onChange={setBoardFilters} compact />
        </div>
      )}

      {showAdvanced && (
        <div className="intraday-advanced-panel">
          <button type="button" className="secondary-button" onClick={() => void handleMorning()} disabled={loading}>
            One-click (board + session)
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={loading || boardLoading}
            onClick={() => {
              void (async () => {
                const syms = [
                  ...(morningBoard?.ranked_stocks || []).map((r) => r.symbol),
                  ...(morningBoard?.ranked_etfs || []).map((r) => r.symbol),
                ].slice(0, 80)
                if (!syms.length) {
                  setError('Run Morning board first')
                  return
                }
                const res = await ensure1mActiveSet(baseUrl, syms)
                if (!res.ok) setError(res.detail || 'ensure-1m failed')
                else setError('')
              })()
            }}
          >
            Ensure 1m
          </button>
          {session?.id && (
            <button type="button" className="secondary-button" onClick={() => void handleReload()} disabled={loading}>
              Reload session
            </button>
          )}
          {session && (
            <button type="button" className="secondary-button" onClick={() => downloadSessionCsv(session)}>
              Export CSV
            </button>
          )}
        </div>
      )}

      {error && <div className="status error">{error}</div>}

      {morningBoard && (
        <section className="intraday-section intraday-morning-section">
          <div className="intraday-section-head">
            <div>
              <h2>Morning board</h2>
              <p className="intraday-phase-line">
                Phase:{' '}
                <span className="phase-pill">{morningBoard.phase_label || morningBoard.phase}</span>
                {morningBoard.phase_label?.toLowerCase().includes('or') || morningBoard.phase ? (
                  <span className="field-hint"> · OR window {ORB_V1_RULES.orWindow}</span>
                ) : null}
              </p>
            </div>
            <div className="intraday-section-tools">
              <label className="intraday-auto-refresh">
                <input
                  type="checkbox"
                  checked={boardAutoRefresh}
                  onChange={(e) => setBoardAutoRefresh(e.target.checked)}
                />
                Auto-refresh
              </label>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void loadMorningBoard()}
                disabled={boardLoading}
              >
                Refresh
              </button>
              <span className="universe-chip">Stocks {morningBoard.universe_stocks}</span>
              <span className="universe-chip">ETFs {morningBoard.universe_etfs}</span>
            </div>
          </div>
          <p className="intraday-board-caption">Stocks vs ETFs ranked separately · Rank is RVOL5 order</p>
          <div className="intraday-board-grid">
            <MorningRankTable
              title="Stocks"
              rows={morningBoard.ranked_stocks}
              empty="No ranked stocks"
              onExplain={setExplainSymbol}
            />
            <MorningRankTable
              title="ETFs"
              rows={morningBoard.ranked_etfs}
              empty="No ranked ETFs"
              onExplain={setExplainSymbol}
            />
          </div>
        </section>
      )}

      {session && (
        <section className="intraday-section intraday-ledger-section">
          <div className="intraday-section-head">
            <div>
              <h2>Session ledger</h2>
              <p className="intraday-meta-line">
                <span>Date {session.session_date}</span>
                <span>Source {session.data_source ?? source}</span>
                <span>Universe {universeLabel}</span>
                <span>Capital {formatInr(accountEquity)}</span>
              </p>
            </div>
            <div className="intraday-section-tools">
              <button
                type="button"
                className="secondary-button"
                onClick={() => void loadMorningBoard()}
                disabled={boardLoading || loading}
              >
                Morning board
              </button>
              <button type="button" className="primary-button" onClick={() => void handleRun()} disabled={loading}>
                {loading ? 'Running…' : 'Run session'}
              </button>
            </div>
          </div>

          <div className="intraday-outcome-chips" role="group" aria-label="Outcome filter">
            {(
              [
                ['ALL', 'ALL'],
                ['TRADED', 'TRADED'],
                ['ARMED', 'ARMED'],
                ['BLOCKED', 'BLOCKED'],
                ['SKIPPED', 'SKIPPED'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`outcome-chip ${outcomeFilter === key ? 'active' : ''}`}
                onClick={() => setOutcomeFilter(key)}
              >
                {label}
                {key !== 'ALL' ? ` ${counts[key]}` : ''}
              </button>
            ))}
            <span className="intraday-chip-note">No profit target</span>
          </div>

          <div className="intraday-kpi-strip">
            <div className="kpi-item">
              <strong>{coverageLabel}</strong>
              <span>Coverage</span>
            </div>
            <div className="kpi-item">
              <strong>{session.fills.length}</strong>
              <span>Fills</span>
            </div>
            <div className="kpi-item">
              <strong>{counts.ARMED}</strong>
              <span>Armed</span>
            </div>
            <div className="kpi-item">
              <strong className={closedPnl >= 0 ? 'pnl-pos' : 'pnl-neg'}>{formatInr(closedPnl)}</strong>
              <span>Closed P/L</span>
            </div>
          </div>

          {highlightRows.length > 0 && (
            <div className="confirmed-box intraday-table-box">
              <div className="table-toolbar">
                <div>
                  <h3>Ready to trade now</h3>
                  <p className="field-hint">
                    Showing {highlightRows.length} of {highlightRows.length} top ideas (Top-{ORB_V1_RULES.topN}{' '}
                    armed plus traded). Rank is RVOL order. Flatten by {ORB_V1_RULES.flatten}.
                  </p>
                </div>
              </div>
              <div className="table-wrap scan-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Stock</th>
                      <th>Trade type</th>
                      <th>Buy/sell at</th>
                      <th>Safety exit</th>
                      <th>Shares</th>
                      <th>₹ at risk</th>
                      <th>Why this idea</th>
                      <th>How decided</th>
                    </tr>
                  </thead>
                  <tbody>
                    {highlightRows.map((row) => {
                      const fill = fillsBySymbol.get(row.symbol)
                      const closed = closedBySymbol.get(row.symbol)
                      const isShort = row.direction === 'SHORT'
                      const open = explainSymbol === row.symbol
                      const why = [
                        orbReasonHint(row.reason) || orbReasonLabel(row.reason),
                        row.rvol5 != null ? `RVOL5 ${Number(row.rvol5).toFixed(2)}` : null,
                        closed
                          ? `Finished ${exitReasonLabel(closed.exit_reason)} · ${formatInr(closed.pnl)}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')
                      return (
                        <tr key={`${row.symbol}-${row.reason}`}>
                          <td className="num-cell">
                            <span className="rank-badge">#{row.rank ?? '—'}</span>
                          </td>
                          <td className="symbol-cell">
                            <button
                              type="button"
                              className="symbol-link"
                              onClick={() => setExplainSymbol(row.symbol)}
                            >
                              {row.symbol}
                            </button>
                          </td>
                          <td>
                            {row.direction ? (
                              <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                {directionLabel(row.direction)}
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="num-cell">{fill ? formatInr(fill.entry) : '—'}</td>
                          <td className="num-cell">{fill ? formatInr(fill.stop) : '—'}</td>
                          <td className="num-cell">{fill ? fill.quantity : '—'}</td>
                          <td className="num-cell">
                            {fill?.risk_amount != null ? formatInr(fill.risk_amount) : '—'}
                          </td>
                          <td className="why-eligible" title={row.detail ?? undefined}>
                            {why || '—'}
                          </td>
                          <td className="deduction-cell">
                            <button
                              type="button"
                              className={`ghost-btn deduction-toggle${open ? ' is-open' : ''}`}
                              onClick={() =>
                                setExplainSymbol((current) => (current === row.symbol ? null : row.symbol))
                              }
                            >
                              {open ? 'Hide steps' : 'How decided'}
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {explainRow && explainSteps && (
            <div className="intraday-evidence-split">
              <div className="confirmed-box intraday-evidence-panel">
                <div className="table-toolbar">
                  <div>
                    <h3>Evidence chart · {explainRow.symbol}</h3>
                    <p className="field-hint">
                      Opening-range high/low solid · buy/sell & safety dashed. No profit-goal line in V1.
                    </p>
                  </div>
                  <div className="table-toolbar-actions">
                    <button
                      type="button"
                      className={chartTf === '1m' ? 'primary-button' : 'secondary-button'}
                      onClick={() => setChartTf('1m')}
                    >
                      1m
                    </button>
                    <button
                      type="button"
                      className={chartTf === '5m' ? 'primary-button' : 'secondary-button'}
                      onClick={() => setChartTf('5m')}
                    >
                      5m
                    </button>
                  </div>
                </div>
                {chartLoading && <p className="field-hint">Loading chart…</p>}
                {chartError && <div className="status error">{chartError}</div>}
                {chart && !chartLoading && (
                  <>
                    <div className="intraday-or-facts">
                      <span>OR high {formatInr(chart.or_high)}</span>
                      <span>OR low {formatInr(chart.or_low)}</span>
                      {chart.entry && <span>Buy/sell {formatInr(chart.entry)}</span>}
                      {chart.stop && <span>Safety {formatInr(chart.stop)}</span>}
                      <span>{chart.candles.length} bars</span>
                      <span>{chart.data_source}</span>
                    </div>
                    <OrbChart
                      candles={chart.candles}
                      levels={{
                        orHigh: chart.or_high,
                        orLow: chart.or_low,
                        entry: chart.entry,
                        stop: chart.stop,
                        exit: chart.exit,
                        triggerIndex: chart.trigger_index,
                      }}
                    />
                  </>
                )}
                <p className="intraday-evidence-foot">
                  V1 flattens by {ORB_V1_RULES.flatten} · no profit target
                </p>
              </div>
              <PlanDeductionPanel
                symbol={explainRow.symbol}
                steps={explainSteps}
                baseUrl={baseUrl}
                onClose={() => setExplainSymbol(null)}
              />
            </div>
          )}

          <div className="intraday-tables-stack">
            <div className="confirmed-box intraday-table-box">
              <div className="table-toolbar">
                <button
                  type="button"
                  className="intraday-collapse-toggle"
                  onClick={() => setLedgerOpen((v) => !v)}
                  aria-expanded={ledgerOpen}
                >
                  <span className={`collapse-caret ${ledgerOpen ? 'open' : ''}`} aria-hidden>
                    ▾
                  </span>
                  <div>
                    <h3>Symbol ledger</h3>
                    <p className="field-hint">
                      Showing {Math.min(ledgerVisibleCount, filteredLedger.length)} of {filteredLedger.length}
                      {outcomeFilter !== 'ALL' ? ` · filter ${outcomeFilter}` : ''}. Rank is RVOL order.
                    </p>
                  </div>
                </button>
                <div className="table-toolbar-actions">
                  <button type="button" className="secondary-button" onClick={() => downloadSessionCsv(session)}>
                    Export CSV
                  </button>
                </div>
              </div>
              {ledgerOpen &&
                (filteredLedger.length === 0 ? (
                  <div className="empty-state">
                    <strong>No rows for this filter</strong>
                    <span>Try ALL or another outcome chip above.</span>
                  </div>
                ) : (
                  <>
                    <div className="table-wrap scan-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Rank</th>
                            <th>Stock</th>
                            <th>Trade type</th>
                            <th>RVOL5</th>
                            <th>Outcome</th>
                            <th>Why this idea</th>
                            <th>How decided</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleLedger.map((row) => {
                            const isShort = row.direction === 'SHORT'
                            const open = explainSymbol === row.symbol
                            return (
                              <tr key={`${row.symbol}-${row.reason}`}>
                                <td className="num-cell">
                                  <span className="rank-badge">#{row.rank ?? '—'}</span>
                                </td>
                                <td className="symbol-cell">
                                  <button
                                    type="button"
                                    className="symbol-link"
                                    onClick={() => setExplainSymbol(row.symbol)}
                                  >
                                    {row.symbol}
                                  </button>
                                </td>
                                <td>
                                  {row.direction ? (
                                    <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                      {directionLabel(row.direction)}
                                    </span>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                                <td className="num-cell">
                                  {row.rvol5 != null ? Number(row.rvol5).toFixed(2) : '—'}
                                </td>
                                <td>
                                  <span className={reasonTone(row.reason)} title={row.reason}>
                                    {orbReasonLabel(row.reason)}
                                  </span>
                                </td>
                                <td className="why-eligible" title={row.detail ?? undefined}>
                                  {orbReasonHint(row.reason) || row.detail || '—'}
                                </td>
                                <td className="deduction-cell">
                                  <button
                                    type="button"
                                    className={`ghost-btn deduction-toggle${open ? ' is-open' : ''}`}
                                    onClick={() =>
                                      setExplainSymbol((current) =>
                                        current === row.symbol ? null : row.symbol,
                                      )
                                    }
                                  >
                                    {open ? 'Hide steps' : 'How decided'}
                                  </button>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                    {filteredLedger.length > 10 && (
                      <div className="ledger-more-row">
                        {ledgerVisibleCount < filteredLedger.length ? (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              setLedgerVisibleCount((n) => Math.min(n + 10, filteredLedger.length))
                            }
                          >
                            See more ({Math.min(10, filteredLedger.length - ledgerVisibleCount)} more)
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => setLedgerVisibleCount(10)}
                          >
                            Show less
                          </button>
                        )}
                      </div>
                    )}
                  </>
                ))}
            </div>

            <div className="confirmed-box intraday-table-box">
              <div className="table-toolbar">
                <button
                  type="button"
                  className="intraday-collapse-toggle"
                  onClick={() => setFillsOpen((v) => !v)}
                  aria-expanded={fillsOpen}
                >
                  <span className={`collapse-caret ${fillsOpen ? 'open' : ''}`} aria-hidden>
                    ▾
                  </span>
                  <div>
                    <h3>Trade plans (fills)</h3>
                    <p className="field-hint">
                      Buy/sell · safety exit · shares. Flatten by {ORB_V1_RULES.flatten}.
                    </p>
                  </div>
                </button>
              </div>
              {fillsOpen &&
                (session.fills.length === 0 ? (
                  <div className="empty-state">
                    <strong>No fills this session</strong>
                    <span>Check Armed / waiting, or try Demo sample.</span>
                  </div>
                ) : (
                  <div className="table-wrap scan-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Stock</th>
                          <th>Trade type</th>
                          <th>Buy/sell at</th>
                          <th>Safety exit</th>
                          <th>Shares</th>
                          <th>₹ at risk</th>
                          <th>How decided</th>
                        </tr>
                      </thead>
                      <tbody>
                        {session.fills.map((fill) => {
                          const isShort = fill.direction === 'SHORT'
                          const open = explainSymbol === fill.symbol
                          return (
                            <tr key={`${fill.symbol}-${fill.trigger_bar_open}`}>
                              <td className="num-cell">
                                <span className="rank-badge">#{fill.rank}</span>
                              </td>
                              <td className="symbol-cell">
                                <button
                                  type="button"
                                  className="symbol-link"
                                  onClick={() => setExplainSymbol(fill.symbol)}
                                >
                                  {fill.symbol}
                                </button>
                              </td>
                              <td>
                                <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                  {directionLabel(fill.direction)}
                                </span>
                              </td>
                              <td className="num-cell">{formatInr(fill.entry)}</td>
                              <td className="num-cell">{formatInr(fill.stop)}</td>
                              <td className="num-cell">{fill.quantity}</td>
                              <td className="num-cell">{formatInr(fill.risk_amount)}</td>
                              <td className="deduction-cell">
                                <button
                                  type="button"
                                  className={`ghost-btn deduction-toggle${open ? ' is-open' : ''}`}
                                  onClick={() =>
                                    setExplainSymbol((current) =>
                                      current === fill.symbol ? null : fill.symbol,
                                    )
                                  }
                                >
                                  {open ? 'Hide steps' : 'How decided'}
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ))}
            </div>

            <div className="confirmed-box intraday-table-box">
              <div className="table-toolbar">
                <button
                  type="button"
                  className="intraday-collapse-toggle"
                  onClick={() => setFinishedOpen((v) => !v)}
                  aria-expanded={finishedOpen}
                >
                  <span className={`collapse-caret ${finishedOpen ? 'open' : ''}`} aria-hidden>
                    ▾
                  </span>
                  <div>
                    <h3>Finished trades</h3>
                    <p className="field-hint">Safety exit or forced 15:10 flatten.</p>
                  </div>
                </button>
              </div>
              {finishedOpen &&
                (session.closed_trades.length === 0 ? (
                  <div className="empty-state">
                    <strong>No finished trades yet</strong>
                    <span>Closed trades appear after stop or 15:10 flatten.</span>
                  </div>
                ) : (
                  <div className="table-wrap scan-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Stock</th>
                          <th>Trade type</th>
                          <th>Buy/sell at</th>
                          <th>Exit</th>
                          <th>How it ended</th>
                          <th>P/L</th>
                          <th>MFE</th>
                          <th>MAE</th>
                          <th>Giveback</th>
                          <th>Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {session.closed_trades.map((trade) => {
                          const isShort = trade.direction === 'SHORT'
                          return (
                            <tr key={`${trade.symbol}-${trade.exit_time}`}>
                              <td className="symbol-cell">
                                <button
                                  type="button"
                                  className="symbol-link"
                                  onClick={() => setExplainSymbol(trade.symbol)}
                                >
                                  {trade.symbol}
                                </button>
                              </td>
                              <td>
                                <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                  {directionLabel(trade.direction)}
                                </span>
                              </td>
                              <td className="num-cell">{formatInr(trade.entry)}</td>
                              <td className="num-cell">{formatInr(trade.exit)}</td>
                              <td>{exitReasonLabel(trade.exit_reason)}</td>
                              <td className={`num-cell ${Number(trade.pnl) >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>
                                {formatInr(trade.pnl)}
                              </td>
                              <td className="num-cell">{formatInr(trade.mfe)}</td>
                              <td className="num-cell">{formatInr(trade.mae)}</td>
                              <td className="num-cell">
                                {trade.giveback != null
                                  ? `${(Number(trade.giveback) * 100).toFixed(0)}%`
                                  : '—'}
                              </td>
                              <td className="muted-cell">
                                {(trade.exit_time ?? '').replace('T', ' ').slice(0, 19)}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ))}
            </div>
          </div>

          {session.fills.length > 0 && (
            <div className="confirmed-box intraday-table-box intraday-practice-box">
              <div className="table-toolbar">
                <div>
                  <h3>Practice fills</h3>
                  <p className="field-hint">
                    {practiceClaim || orbPaperClaim()}
                    {divergence
                      ? ` · divergence gap ${formatInr(divergence.pnl_gap_sum)} · matched ${divergence.matched_closed}/${divergence.total_model_closed}`
                      : ''}
                  </p>
                </div>
                <div className="table-toolbar-actions">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={practiceBusy || session.fills.length === 0}
                    onClick={() => void handleSeedPractice()}
                  >
                    {practiceBusy ? 'Working…' : 'Seed practice'}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={practiceBusy || practice.every((t) => t.status !== 'OPEN')}
                    onClick={() => void handlePracticeTick(false, true)}
                  >
                    Tick LTP
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={practiceBusy || practice.every((t) => t.status !== 'OPEN')}
                    onClick={() => void handlePracticeTick(true, false)}
                  >
                    Flatten 15:10
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={practiceBusy}
                    onClick={() => void handleDivergence()}
                  >
                    Reconcile
                  </button>
                </div>
              </div>
              {practice.length === 0 ? (
                <div className="empty-state">
                  <strong>No practice rows yet</strong>
                  <span>Seed practice from this session’s fills to paper-track marks and P/L.</span>
                </div>
              ) : (
                <div className="table-wrap scan-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Stock</th>
                        <th>Trade type</th>
                        <th>Status</th>
                        <th>Buy/sell at</th>
                        <th>Safety exit</th>
                        <th>Shares</th>
                        <th>Live mark</th>
                        <th>P/L</th>
                        <th>How ended</th>
                      </tr>
                    </thead>
                    <tbody>
                      {practice.map((trade) => {
                        const isShort = trade.direction === 'SHORT'
                        const pnl = Number(
                          trade.status === 'OPEN' ? trade.unrealized_pnl : trade.realized_pnl,
                        )
                        return (
                          <tr key={trade.id}>
                            <td className="symbol-cell">
                              <button
                                type="button"
                                className="symbol-link"
                                onClick={() => setExplainSymbol(trade.symbol)}
                              >
                                {trade.symbol}
                              </button>
                            </td>
                            <td>
                              <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                                {directionLabel(trade.direction)}
                              </span>
                            </td>
                            <td>{trade.status === 'OPEN' ? 'In trade' : 'Finished'}</td>
                            <td className="num-cell">{formatInr(trade.entry_price)}</td>
                            <td className="num-cell">{formatInr(trade.stop_loss)}</td>
                            <td className="num-cell">{trade.quantity}</td>
                            <td className="num-cell">{formatInr(trade.last_mark_price)}</td>
                            <td className={`num-cell ${pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>
                              {formatInr(pnl)}
                            </td>
                            <td>{trade.exit_reason ? exitReasonLabel(trade.exit_reason) : '—'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {divergence && (
                <div className="intraday-reconcile-strip">
                  Practice vs model · matched closed {divergence.matched_closed}/
                  {divergence.total_model_closed} · halt stub Off
                </div>
              )}
              <div className="intraday-claim-banner">
                <span className="claim-shield" aria-hidden />
                <span>{practiceClaim || orbPaperClaim()}</span>
              </div>
            </div>
          )}
        </section>
      )}

      <CoverageDrawer
        open={coverageOpen}
        onClose={() => setCoverageOpen(false)}
        baseUrl={baseUrl}
        universe={universe === 'CUSTOM' || universe === 'DEMO_SAMPLE' ? 'NSE_ALL' : universe}
        filters={boardFilters}
        dataAsOf={null}
        formatDateTime={(value) => {
          if (!value) return '—'
          try {
            return new Date(value).toLocaleString('en-IN')
          } catch {
            return value
          }
        }}
      />

      <footer className="intraday-desk-footer">
        <span className="claim-shield" aria-hidden />
        <span>Informational only — not brokerage advice.</span>
      </footer>
    </section>
  )
}
