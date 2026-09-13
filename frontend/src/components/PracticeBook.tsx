import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  closePracticeTrade,
  listIntradayPractice,
  listIntradaySessions,
  tickIntradayPractice,
  type IntradayPracticeTrade,
} from '../intraday/api'
import { directionLabel, PAPER_CLAIM } from '../terminology'
import { TradeDurationTimer } from './TradeDurationTimer'

type SwingPaperRow = {
  id: number
  symbol: string
  status: string
  direction?: string
  entry_price?: string | number
  stop_loss?: string | number
  target?: string | number
  quantity?: number
  risk_amount?: string | number | null
  realized_pnl?: string | number | null
  unrealized_pnl?: string | number | null
  last_mark_price?: string | number | null
  exit_price?: string | number | null
  exit_reason?: string | null
  opened_at?: string | null
  closed_at?: string | null
  created_at?: string | null
  setup_name?: string | null
}

type StatusFilter = 'ALL' | 'OPEN' | 'CLOSED' | 'PENDING'
type PracticeRow = SwingPaperRow | IntradayPracticeTrade

type Props = {
  baseUrl: string
  swingEquity: string
  intradayEquity: string
  reserveEquity?: string
  paperTradingEnabled?: boolean
  onEnablePaper?: () => void
  onTradesChanged?: () => void
  /** Fired whenever wallets recompute (load / close / tick) so sizing uses live capital. */
  onLiveCapitalChange?: (next: { swing: number; intraday: number }) => void
  onOpenSwing?: () => void
  onOpenIntraday?: () => void
}

const CLAIM_KEY = 'tp_practice_claim_ack'

function formatPrice(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(n)
}

function formatSigned(value: number): string {
  const abs = formatPrice(Math.abs(value))
  if (value > 0) return `+${abs}`
  if (value < 0) return `-${abs}`
  return abs
}

function formatElapsedBetween(startIso: string | null | undefined, endIso: string | null | undefined): string {
  if (!startIso) return '—'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—'
  const totalSec = Math.floor((end - start) / 1000)
  if (totalSec < 60) return totalSec <= 0 ? 'same tick' : `<1m`
  const hours = Math.floor(totalSec / 3600)
  const minutes = Math.floor((totalSec % 3600) / 60)
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function statusClass(status: string): string {
  const s = normalizeStatus(status).toLowerCase()
  if (s === 'open' || s === 'pending') return s
  if (s === 'closed') return 'closed'
  return 'muted'
}

function normalizeStatus(status: string | null | undefined): string {
  return String(status || '').trim().toUpperCase()
}

function tradeQty(t: PracticeRow): number {
  const qty = Number(t.quantity)
  return Number.isFinite(qty) && qty > 0 ? qty : 0
}

function tradePnl(t: PracticeRow): number {
  const entry = Number(t.entry_price)
  const qty = tradeQty(t)
  const direction = String(t.direction || '').toUpperCase()
  const status = normalizeStatus(t.status)

  if (status === 'OPEN' || status === 'PENDING') {
    const mark = Number(t.last_mark_price)
    if (Number.isFinite(entry) && Number.isFinite(mark) && qty > 0) {
      const computed = direction === 'SHORT' ? (entry - mark) * qty : (mark - entry) * qty
      if (Number.isFinite(computed)) return computed
    }
    const server = Number(t.unrealized_pnl)
    return Number.isFinite(server) ? server : 0
  }

  // Closed: prefer entry/exit/qty so table PnL matches displayed prices & shares
  const exit = Number(t.exit_price ?? t.last_mark_price)
  if (Number.isFinite(entry) && Number.isFinite(exit) && qty > 0) {
    const computed = direction === 'SHORT' ? (entry - exit) * qty : (exit - entry) * qty
    if (Number.isFinite(computed)) return computed
  }
  const server = Number(t.realized_pnl)
  return Number.isFinite(server) ? server : 0
}

/** Notional capital tied to the trade (entry × shares) — shown for open and closed. */
function tradeUsedCapital(t: PracticeRow): number {
  const entry = Number(t.entry_price)
  const qty = tradeQty(t)
  if (!Number.isFinite(entry) || entry <= 0 || qty <= 0) return 0
  return entry * qty
}

function summarizeWallet(trades: PracticeRow[], startingCapital: number) {
  const start = Number.isFinite(startingCapital) && startingCapital > 0 ? startingCapital : 0
  let usedOpen = 0
  let reserved = 0
  let live = 0
  let realized = 0
  let openCount = 0
  let closedNotional = 0
  for (const trade of trades) {
    const status = normalizeStatus(trade.status)
    if (status === 'OPEN') {
      openCount += 1
      usedOpen += tradeUsedCapital(trade)
      live += tradePnl(trade)
    } else if (status === 'PENDING') {
      openCount += 1
      reserved += tradeUsedCapital(trade)
    } else if (status === 'CLOSED') {
      realized += tradePnl(trade)
      closedNotional += tradeUsedCapital(trade)
    }
  }
  // Cash free after closed PnL, with open notionals still locked
  const remaining = start + realized - usedOpen - reserved
  return {
    starting: start,
    usedOpen,
    reserved,
    closedNotional,
    remaining,
    live,
    realized,
    equity: remaining + usedOpen + reserved + live,
    openCount,
  }
}

function isLiveStatus(status: string): boolean {
  const s = normalizeStatus(status)
  return s === 'OPEN' || s === 'PENDING'
}

export function PracticeBook({
  baseUrl,
  swingEquity,
  intradayEquity,
  reserveEquity,
  paperTradingEnabled = true,
  onEnablePaper,
  onTradesChanged,
  onLiveCapitalChange,
  onOpenSwing,
  onOpenIntraday,
}: Props) {
  const [tab, setTab] = useState<'swing' | 'intraday'>('swing')
  const [swing, setSwing] = useState<SwingPaperRow[]>([])
  const [intraday, setIntraday] = useState<IntradayPracticeTrade[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyAction, setBusyAction] = useState<'refresh' | 'tick' | 'reset' | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')
  const [timerPaused, setTimerPaused] = useState(false)
  const [pausedAtMs, setPausedAtMs] = useState<number | null>(null)
  const [claimAck, setClaimAck] = useState(() => {
    try {
      return localStorage.getItem(CLAIM_KEY) === '1'
    } catch {
      return false
    }
  })

  const onTradesChangedRef = useRef(onTradesChanged)
  onTradesChangedRef.current = onTradesChanged
  const onLiveCapitalChangeRef = useRef(onLiveCapitalChange)
  onLiveCapitalChangeRef.current = onLiveCapitalChange
  const loadGenRef = useRef(0)

  const notifyParent = useCallback(() => {
    onTradesChangedRef.current?.()
  }, [])

  const load = useCallback(
    async (opts?: { notify?: boolean; action?: 'refresh' | 'tick' }) => {
      const gen = ++loadGenRef.current
      if (opts?.action) setBusyAction(opts.action)
      setError('')
      try {
        const paperRes = await fetch(`${baseUrl}/api/v1/paper/trades?status=ALL`)
        if (gen !== loadGenRef.current) return
        if (paperRes.ok) {
          const body = (await paperRes.json()) as { trades?: SwingPaperRow[]; claim?: string }
          setSwing(body.trades || [])
        } else {
          setError(`Swing practice load failed (${paperRes.status})`)
        }
        const { sessions } = await listIntradaySessions(baseUrl, 12)
        if (gen !== loadGenRef.current) return
        const all: IntradayPracticeTrade[] = []
        for (const s of sessions) {
          try {
            const listed = await listIntradayPractice(baseUrl, s.id)
            all.push(...listed.trades)
          } catch {
            /* skip session without practice rows */
          }
        }
        if (gen !== loadGenRef.current) return
        setIntraday(all)
        if (opts?.notify) notifyParent()
      } catch (err) {
        if (gen !== loadGenRef.current) return
        setError(err instanceof Error ? err.message : 'Failed to load practice book')
      } finally {
        if (gen === loadGenRef.current) setBusyAction(null)
      }
    },
    [baseUrl, notifyParent],
  )

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setSelectedId(null)
    setDetailOpen(false)
    setTimerPaused(false)
    setPausedAtMs(null)
    setStatusFilter('ALL')
  }, [tab])

  const autoIntraTickRef = useRef(false)
  useEffect(() => {
    if (tab !== 'intraday') {
      autoIntraTickRef.current = false
      return
    }
    if (autoIntraTickRef.current || busyAction) return
    const sessionIds = [
      ...new Set(intraday.filter((t) => t.status === 'OPEN' && t.session_id).map((t) => t.session_id)),
    ]
    if (sessionIds.length === 0) return
    autoIntraTickRef.current = true
    let cancelled = false
    void (async () => {
      try {
        for (const sessionId of sessionIds) {
          await tickIntradayPractice(baseUrl, sessionId, { use_live_quotes: true })
        }
        if (!cancelled) await load({ notify: true })
      } catch {
        /* keep listed marks if live quotes unavailable */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [tab, intraday, busyAction, baseUrl, load])

  useEffect(() => {
    if (!detailOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDetailOpen(false)
        setSelectedId(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [detailOpen])

  const rows = tab === 'swing' ? swing : intraday

  const filtered = useMemo(() => {
    if (statusFilter === 'ALL') return rows
    return rows.filter((t) => normalizeStatus(t.status) === statusFilter)
  }, [rows, statusFilter])

  const walletDesk = useMemo(
    () =>
      summarizeWallet(
        rows as PracticeRow[],
        Number(tab === 'swing' ? swingEquity : intradayEquity) || 0,
      ),
    [rows, tab, swingEquity, intradayEquity],
  )
  const swingWallet = useMemo(
    () => summarizeWallet(swing, Number(swingEquity) || 0),
    [swing, swingEquity],
  )
  const intraWallet = useMemo(
    () => summarizeWallet(intraday, Number(intradayEquity) || 0),
    [intraday, intradayEquity],
  )

  useEffect(() => {
    // Cash equity after closes: allocated + realized (used by sizing / parent)
    const swingLive = Math.max(0, swingWallet.starting + swingWallet.realized)
    const intradayLive = Math.max(0, intraWallet.starting + intraWallet.realized)
    onLiveCapitalChangeRef.current?.({ swing: swingLive, intraday: intradayLive })
  }, [
    swingWallet.starting,
    swingWallet.realized,
    intraWallet.starting,
    intraWallet.realized,
  ])

  const selectedSwing = tab === 'swing' ? swing.find((t) => t.id === selectedId) ?? null : null
  const selectedIntra = tab === 'intraday' ? intraday.find((t) => t.id === selectedId) ?? null : null
  const selected = selectedSwing || selectedIntra
  const selectedPnl = selected ? tradePnl(selected) : 0
  const selectedUsed = selected ? tradeUsedCapital(selected) : 0

  function openDetail(id: number) {
    setSelectedId(id)
    setDetailOpen(true)
    setTimerPaused(false)
    setPausedAtMs(null)
  }

  function closeDetail() {
    setDetailOpen(false)
    setSelectedId(null)
    setTimerPaused(false)
    setPausedAtMs(null)
  }

  function toggleTimer() {
    if (!selected || normalizeStatus(selected.status) !== 'OPEN') return
    if (timerPaused) {
      setTimerPaused(false)
      setPausedAtMs(null)
      return
    }
    setTimerPaused(true)
    setPausedAtMs(Date.now())
  }

  async function resetPracticeBook() {
    const ok = window.confirm(
      'Start fresh? This deletes all Swing and Intraday practice trades. Capitals stay the same; wallets reset to starting amounts.',
    )
    if (!ok) return
    setError('')
    setNotice('')
    setBusyAction('reset')
    try {
      const [swingRes, intraRes] = await Promise.all([
        fetch(`${baseUrl}/api/v1/paper/trades`, { method: 'DELETE' }),
        fetch(`${baseUrl}/api/v1/intraday/practice`, { method: 'DELETE' }),
      ])
      if (!swingRes.ok) throw new Error('Failed to clear swing practice trades')
      if (!intraRes.ok) throw new Error('Failed to clear intraday practice trades')
      const swingBody = (await swingRes.json()) as { deleted?: number }
      const intraBody = (await intraRes.json()) as { deleted?: number }
      setNotice(
        `Practice cleared — removed ${swingBody.deleted ?? 0} swing and ${intraBody.deleted ?? 0} intraday trades. Wallets start fresh.`,
      )
      closeDetail()
      await load({ notify: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
      setBusyAction(null)
    }
  }

  function claimFakeMoney() {
    try {
      localStorage.setItem(CLAIM_KEY, '1')
    } catch {
      /* ignore */
    }
    setClaimAck(true)
    setNotice(
      `${PAPER_CLAIM} Swing capital ₹${formatPrice(swingEquity || 0)} · Intraday capital ₹${formatPrice(intradayEquity || 0)}${reserveEquity ? ` · Reserve ₹${formatPrice(reserveEquity)} (not deployed)` : ''}. Capital available ≠ permission to risk it. No real brokerage order.`,
    )
  }

  async function tickSwing() {
    setError('')
    setNotice('')
    setBusyAction('tick')
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/tick`, { method: 'POST' })
      if (!response.ok) throw new Error('Swing tick failed')
      setNotice('Live marks refreshed for swing practice.')
      await load({ notify: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tick failed')
      setBusyAction(null)
    }
  }

  async function tickOpenIntraday(forceEod = false) {
    const sessionIds = [
      ...new Set(
        intraday.filter((t) => t.status === 'OPEN' && t.session_id).map((t) => t.session_id),
      ),
    ]
    if (sessionIds.length === 0) {
      setNotice('No open intraday practice trades to mark.')
      return
    }
    setError('')
    setNotice('')
    setBusyAction('tick')
    try {
      let marks = 0
      for (const sessionId of sessionIds) {
        const result = await tickIntradayPractice(baseUrl, sessionId, {
          force_eod: forceEod,
          use_live_quotes: true,
        })
        marks += result.marks_applied || 0
      }
      setNotice(
        forceEod
          ? 'Intraday practice flattened (15:10).'
          : `Intraday live marks refreshed (${marks} update${marks === 1 ? '' : 's'}).`,
      )
      await load({ notify: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Intraday tick failed')
      setBusyAction(null)
    }
  }

  async function closeSwing(tradeId: number) {
    setBusyId(tradeId)
    setError('')
    try {
      const response = await fetch(`${baseUrl}/api/v1/paper/trades/${tradeId}/close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error((detail as { detail?: string }).detail || 'Close failed')
      }
      setNotice('Swing practice trade closed.')
      await load({ notify: true })
      closeDetail()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Close failed')
    } finally {
      setBusyId(null)
    }
  }

  async function tickIntra(sessionId: string, forceEod = false) {
    setError('')
    try {
      await tickIntradayPractice(baseUrl, sessionId, {
        force_eod: forceEod,
        use_live_quotes: true,
      })
      setNotice(forceEod ? 'Intraday practice flattened (15:10).' : 'Intraday marks refreshed.')
      await load({ notify: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Intraday tick failed')
    }
  }

  async function closeIntra(trade: IntradayPracticeTrade) {
    setBusyId(trade.id)
    setError('')
    try {
      const mark = trade.last_mark_price || trade.entry_price
      await closePracticeTrade(baseUrl, trade.id, String(mark))
      setNotice(`Closed ${trade.symbol} practice trade.`)
      await load({ notify: true })
      closeDetail()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Close failed')
    } finally {
      setBusyId(null)
    }
  }

  function deskLabel(symbol: string): string {
    if (tab === 'swing') return 'Equity'
    if (/\b(CE|PE)\b/i.test(symbol) || /(?:CE|PE)$/i.test(symbol.replace(/\s+/g, ''))) return 'Options'
    return 'Equity'
  }

  function statusLabel(status: string): string {
    const s = status.toUpperCase()
    if (s === 'OPEN') return 'Open'
    if (s === 'CLOSED') return 'Closed'
    if (s === 'PENDING') return 'Waiting'
    return status
  }

  const headBusy = busyAction !== null

  const detailModal =
    detailOpen && selected
      ? createPortal(
          <div className="practice-detail-overlay" onClick={closeDetail}>
            <div
              className="practice-detail-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="practice-detail-title"
              onClick={(event) => event.stopPropagation()}
            >
              <header className="practice-detail-modal-head">
                <div>
                  <p className="eyebrow">Trade detail</p>
                  <h2 id="practice-detail-title">
                    {selected.symbol}
                    <span className={`status-pill ${statusClass(selected.status)}`}>
                      {statusLabel(selected.status)}
                    </span>
                  </h2>
                  <p className="field-hint">
                    {tab === 'swing' ? 'Swing' : 'Intraday'} · {deskLabel(selected.symbol)}
                    {selected.direction ? ` · ${directionLabel(selected.direction)}` : ''}
                  </p>
                </div>
                <div className="practice-detail-actions">
                  {normalizeStatus(selected.status) === 'OPEN' ? (
                    <button type="button" className="secondary-button" onClick={toggleTimer}>
                      <span className="practice-ico practice-ico-timer" aria-hidden="true" />
                      {timerPaused ? 'Resume timer' : 'Pause timer'}
                    </button>
                  ) : null}
                  <button type="button" className="ghost-btn practice-detail-close" onClick={closeDetail} aria-label="Close">
                    ×
                  </button>
                </div>
              </header>

              <div className="practice-detail-modal-body">
                <div className="practice-detail-kpi-row">
                  <article>
                    <span>Capital used (entry × shares)</span>
                    <strong>₹{formatPrice(selectedUsed)}</strong>
                  </article>
                  <article>
                    <span>Live mark</span>
                    <strong>{formatPrice(selected.last_mark_price)}</strong>
                  </article>
                  <article>
                    <span>{isLiveStatus(selected.status) ? 'Live PnL' : 'Realized PnL'}</span>
                    <strong className={selectedPnl >= 0 ? 'pnl-pos' : 'pnl-neg'}>
                      {formatSigned(selectedPnl)}
                    </strong>
                  </article>
                  <article>
                    <span>Duration</span>
                    <strong>
                      {normalizeStatus(selected.status) === 'OPEN' && selected.opened_at && !timerPaused ? (
                        <TradeDurationTimer startedAt={selected.opened_at} label="" />
                      ) : (
                        formatElapsedBetween(
                          selected.opened_at,
                          selected.closed_at ?? (pausedAtMs ? new Date(pausedAtMs).toISOString() : null),
                        )
                      )}
                    </strong>
                  </article>
                </div>

                <dl className="practice-detail-facts">
                  <div>
                    <dt>Entry</dt>
                    <dd>{formatPrice(selected.entry_price)}</dd>
                  </div>
                  <div>
                    <dt>Stop</dt>
                    <dd>{formatPrice(selected.stop_loss)}</dd>
                  </div>
                  {selectedSwing?.target != null ? (
                    <div>
                      <dt>Target</dt>
                      <dd>{formatPrice(selectedSwing.target)}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>Shares</dt>
                    <dd>{selectedSwing?.quantity ?? selectedIntra?.quantity ?? '—'}</dd>
                  </div>
                  {selected.exit_reason ? (
                    <div>
                      <dt>How ended</dt>
                      <dd>{selected.exit_reason}</dd>
                    </div>
                  ) : null}
                  {selectedIntra?.session_id ? (
                    <div>
                      <dt>Session</dt>
                      <dd>{selectedIntra.session_id.slice(0, 8)}…</dd>
                    </div>
                  ) : null}
                </dl>

                <div className="practice-detail-modal-cta">
                  {selectedSwing && (selectedSwing.status === 'OPEN' || selectedSwing.status === 'PENDING') ? (
                    <button
                      type="button"
                      className="primary-button"
                      disabled={busyId === selectedSwing.id}
                      onClick={() => void closeSwing(selectedSwing.id)}
                    >
                      {busyId === selectedSwing.id ? 'Closing…' : 'Close now'}
                    </button>
                  ) : null}
                  {selectedIntra && selectedIntra.status === 'OPEN' ? (
                    <>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void tickIntra(selectedIntra.session_id, false)}
                      >
                        Tick LTP
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void tickIntra(selectedIntra.session_id, true)}
                      >
                        Flatten 15:10
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        disabled={busyId === selectedIntra.id}
                        onClick={() => void closeIntra(selectedIntra)}
                      >
                        {busyId === selectedIntra.id ? 'Closing…' : 'Close now'}
                      </button>
                    </>
                  ) : null}
                </div>
                <p className="field-hint practice-detail-claim">{PAPER_CLAIM}</p>
              </div>
            </div>
          </div>,
          document.body,
        )
      : null

  return (
    <section className="panel practice-book wireframe-practice" aria-label="Unified Practice Book">
      <header className="header-block practice-book-head">
        <div>
          <p className="eyebrow practice-book-brandline">
            <span className="practice-ico practice-ico-plane" aria-hidden="true" />
            <span>TradePilot</span>
            <span className="practice-brand-sep" aria-hidden="true" />
            <span>Practice</span>
          </p>
          <h1>Unified Practice Book</h1>
          <p className="header-copy">
            Swing and intraday fake-money trades in one place. Engine owns Entry / Stop — nothing goes to a
            broker.
          </p>
        </div>
        <div className="practice-book-head-actions">
          {tab === 'swing' ? (
            <button
              type="button"
              className="secondary-button"
              onClick={() => void tickSwing()}
              disabled={headBusy}
            >
              <span className="practice-ico practice-ico-refresh" aria-hidden="true" />
              {busyAction === 'tick' ? 'Ticking…' : 'Tick marks'}
            </button>
          ) : (
            <button
              type="button"
              className="secondary-button"
              onClick={() => void tickOpenIntraday(false)}
              disabled={headBusy}
            >
              <span className="practice-ico practice-ico-refresh" aria-hidden="true" />
              {busyAction === 'tick' ? 'Ticking…' : 'Tick marks'}
            </button>
          )}
          <button
            type="button"
            className="secondary-button"
            onClick={() => void load({ action: 'refresh' })}
            disabled={headBusy}
          >
            <span className="practice-ico practice-ico-refresh" aria-hidden="true" />
            {busyAction === 'refresh' ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <div className="practice-tabs" role="tablist" aria-label="Practice desk">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'swing'}
          className={tab === 'swing' ? 'practice-tab active' : 'practice-tab'}
          onClick={() => setTab('swing')}
        >
          <span className="practice-ico practice-ico-swing" aria-hidden="true" />
          Swing practice
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'intraday'}
          className={tab === 'intraday' ? 'practice-tab active' : 'practice-tab'}
          onClick={() => setTab('intraday')}
        >
          <span className="practice-ico practice-ico-bolt" aria-hidden="true" />
          Intraday practice
        </button>
      </div>

      {!paperTradingEnabled && tab === 'swing' ? (
        <div className="practice-enable-banner">
          <div>
            <strong>Swing practice is off</strong>
            <p className="field-hint">Turn it on to arm fake trades from Find Setups.</p>
          </div>
          <button type="button" className="primary-button" onClick={() => onEnablePaper?.()}>
            Turn on practice
          </button>
        </div>
      ) : null}

      <div className="practice-wallet" aria-label={`${tab === 'swing' ? 'Swing' : 'Intraday'} capital wallet`}>
        <div className="practice-wallet-head">
          <h3>{tab === 'swing' ? 'Swing capital wallet' : 'Intraday capital wallet'}</h3>
          <p className="field-hint">
            Separate from the other desk · allocated in Capital & risk · updates on every close
          </p>
          <div className="practice-wallet-head-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void resetPracticeBook()}
              disabled={busyAction !== null}
            >
              {busyAction === 'reset' ? 'Clearing…' : 'Start fresh'}
            </button>
            <button type="button" className="primary-button practice-wallet-claim" onClick={claimFakeMoney}>
              {claimAck ? 'Claimed' : 'Claim fake money'}
            </button>
          </div>
        </div>
        {tab === 'swing' ? (
          <div className="paper-capital-strip practice-wallet-strip is-active-desk">
            <div className="practice-wallet-desk-label">Swing</div>
            <div className="paper-capital-metric">
              <span>Allocated</span>
              <strong>₹{formatPrice(swingWallet.starting)}</strong>
              <em>From Capital & risk</em>
            </div>
            <div className="paper-capital-metric">
              <span>Live capital</span>
              <strong>₹{formatPrice(swingWallet.starting + swingWallet.realized)}</strong>
              <em>Allocated + closed PnL · used for sizing</em>
            </div>
            <div>
              <span>Open used</span>
              <strong>₹{formatPrice(swingWallet.usedOpen)}</strong>
              <em>Entry × shares in open trades</em>
            </div>
            <div className="paper-capital-remaining">
              <span>Cash left</span>
              <strong>₹{formatPrice(swingWallet.remaining)}</strong>
              <em>Live capital − open used</em>
            </div>
            <div>
              <span>Live PnL</span>
              <strong className={swingWallet.live >= 0 ? 'pnl-pos' : 'pnl-neg'}>
                {formatSigned(swingWallet.live)}
              </strong>
            </div>
            <div>
              <span>Realized PnL</span>
              <strong className={swingWallet.realized >= 0 ? 'pnl-pos' : 'pnl-neg'}>
                {formatSigned(swingWallet.realized)}
              </strong>
            </div>
            <div>
              <span>Wallet value</span>
              <strong>₹{formatPrice(swingWallet.equity)}</strong>
              <em>Cash + open used + live</em>
            </div>
            {swingWallet.reserved > 0 ? (
              <div>
                <span>Waiting (reserved)</span>
                <strong>₹{formatPrice(swingWallet.reserved)}</strong>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="paper-capital-strip practice-wallet-strip is-active-desk">
            <div className="practice-wallet-desk-label">Intraday</div>
            <div className="paper-capital-metric">
              <span>Allocated</span>
              <strong>₹{formatPrice(intraWallet.starting)}</strong>
              <em>From Capital & risk</em>
            </div>
            <div className="paper-capital-metric">
              <span>Live capital</span>
              <strong>₹{formatPrice(intraWallet.starting + intraWallet.realized)}</strong>
              <em>Allocated + closed PnL · used for sizing</em>
            </div>
            <div>
              <span>Open used</span>
              <strong>₹{formatPrice(intraWallet.usedOpen)}</strong>
              <em>Entry × shares in open trades</em>
            </div>
            <div className="paper-capital-remaining">
              <span>Cash left</span>
              <strong>₹{formatPrice(intraWallet.remaining)}</strong>
              <em>Live capital − open used</em>
            </div>
            <div>
              <span>Live PnL</span>
              <strong className={intraWallet.live >= 0 ? 'pnl-pos' : 'pnl-neg'}>
                {formatSigned(intraWallet.live)}
              </strong>
            </div>
            <div>
              <span>Realized PnL</span>
              <strong className={intraWallet.realized >= 0 ? 'pnl-pos' : 'pnl-neg'}>
                {formatSigned(intraWallet.realized)}
              </strong>
            </div>
            <div>
              <span>Wallet value</span>
              <strong>₹{formatPrice(intraWallet.equity)}</strong>
              <em>Cash + open used + live</em>
            </div>
            {intraWallet.reserved > 0 ? (
              <div>
                <span>Waiting (reserved)</span>
                <strong>₹{formatPrice(intraWallet.reserved)}</strong>
              </div>
            ) : null}
          </div>
        )}
      </div>

      <div className="practice-stats">
        <article className="practice-stat-card">
          <div className="practice-stat-row">
            <span className="practice-stat-ico practice-ico practice-ico-book" aria-hidden="true" />
            <span>{tab === 'swing' ? 'Swing open' : 'Intraday open'}</span>
          </div>
          <strong>{walletDesk.openCount}</strong>
        </article>
        <article className="practice-stat-card">
          <div className="practice-stat-row">
            <span className="practice-stat-ico practice-ico practice-ico-rupee" aria-hidden="true" />
            <span>Desk open used</span>
          </div>
          <strong>₹{formatPrice(walletDesk.usedOpen)}</strong>
        </article>
        <article className="practice-stat-card">
          <div className="practice-stat-row">
            <span className="practice-stat-ico practice-ico practice-ico-pulse" aria-hidden="true" />
            <span>Desk live PnL</span>
          </div>
          <strong className={walletDesk.live >= 0 ? 'pnl-pos' : 'pnl-neg'}>
            {formatSigned(walletDesk.live)}
          </strong>
        </article>
        <article className="practice-stat-card">
          <div className="practice-stat-row">
            <span className="practice-stat-ico practice-ico practice-ico-bars" aria-hidden="true" />
            <span>Desk realized</span>
          </div>
          <strong className={walletDesk.realized >= 0 ? 'pnl-pos' : 'pnl-neg'}>
            {formatSigned(walletDesk.realized)}
          </strong>
        </article>
      </div>

      {notice ? <div className="status ok">{notice}</div> : null}
      {error ? <div className="status error">{error}</div> : null}

      <div className="practice-table-head">
        <h3 className="practice-table-title">
          <span className="practice-ico practice-ico-list" aria-hidden="true" />
          Table of trades
        </h3>
        <div className="practice-status-filters" role="group" aria-label="Status filter">
          {(['ALL', 'PENDING', 'OPEN', 'CLOSED'] as const).map((key) => (
            <button
              key={key}
              type="button"
              className={`practice-filter-chip${statusFilter === key ? ' active' : ''}`}
              onClick={() => setStatusFilter(key)}
            >
              {key === 'PENDING' ? 'Waiting' : key === 'OPEN' ? 'In trade' : key === 'CLOSED' ? 'Finished' : 'All'}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap scan-table-wrap practice-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Desk</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>Stop</th>
              <th>Shares</th>
              <th>Used</th>
              <th>PnL</th>
              <th>Status</th>
              <th>Duration</th>
              <th aria-label="Open detail">
                <span className="practice-ico practice-ico-filter" aria-hidden="true" />
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={11}>
                  <div className="empty-state">
                    <strong>No {tab} practice trades</strong>
                    <span>
                      {tab === 'swing'
                        ? 'Arm ideas from Find Setups, or open Swing to run a scan.'
                        : 'Seed practice from an Intraday session ledger.'}
                    </span>
                    {tab === 'swing' && onOpenSwing ? (
                      <button type="button" className="secondary-button" onClick={onOpenSwing}>
                        Open Find Setups
                      </button>
                    ) : null}
                    {tab === 'intraday' && onOpenIntraday ? (
                      <button type="button" className="secondary-button" onClick={onOpenIntraday}>
                        Open Intraday desk
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((t) => {
                const isShort = t.direction === 'SHORT'
                const open = selectedId === t.id && detailOpen
                const pnl = tradePnl(t)
                const used = tradeUsedCapital(t)
                const qty = tradeQty(t)
                const status = normalizeStatus(t.status)
                const duration =
                  status === 'OPEN' && t.opened_at && !(timerPaused && open) ? (
                    <TradeDurationTimer startedAt={t.opened_at} label="" />
                  ) : status === 'OPEN' && t.opened_at && timerPaused && open && pausedAtMs != null ? (
                    formatElapsedBetween(t.opened_at, new Date(pausedAtMs).toISOString())
                  ) : (
                    formatElapsedBetween(t.opened_at, t.closed_at)
                  )
                return (
                  <tr
                    key={`${tab}-${t.id}`}
                    className={open ? 'row-selected' : undefined}
                    onClick={() => openDetail(t.id)}
                  >
                    <td className="symbol-cell">
                      <button type="button" className="symbol-link" onClick={() => openDetail(t.id)}>
                        {t.symbol}
                      </button>
                    </td>
                    <td>{deskLabel(t.symbol)}</td>
                    <td>
                      {t.direction ? (
                        <span className={`direction-pill ${isShort ? 'short' : 'long'}`}>
                          <span
                            className={`practice-ico ${isShort ? 'practice-ico-down' : 'practice-ico-up'}`}
                            aria-hidden="true"
                          />
                          {directionLabel(t.direction)}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="num-cell">{formatPrice(t.entry_price)}</td>
                    <td className="num-cell">{formatPrice(t.stop_loss)}</td>
                    <td className="num-cell">{qty > 0 ? qty.toLocaleString('en-IN') : '—'}</td>
                    <td className="num-cell">{used > 0 ? `₹${formatPrice(used)}` : '—'}</td>
                    <td className={`num-cell ${pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>{formatSigned(pnl)}</td>
                    <td>
                      <span className={`status-pill ${statusClass(t.status)}`}>{statusLabel(t.status)}</span>
                    </td>
                    <td className="muted-cell">{duration}</td>
                    <td>
                      <button
                        type="button"
                        className="ghost-btn practice-row-open"
                        aria-label={`Open ${t.symbol} detail`}
                        onClick={(e) => {
                          e.stopPropagation()
                          openDetail(t.id)
                        }}
                      >
                        <span className="practice-ico practice-ico-chevron" aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {detailModal}

      <footer className="practice-footer-claim">
        <span className="practice-ico practice-ico-shield" aria-hidden="true" />
        <span>Practice is not a brokerage order. This is a simulated learning environment.</span>
      </footer>
    </section>
  )
}
