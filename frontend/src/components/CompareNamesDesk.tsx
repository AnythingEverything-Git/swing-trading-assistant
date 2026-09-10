import { useEffect, useMemo, useState } from 'react'
import { directionLabel } from '../terminology'

type CompareSide = {
  symbol: string
  direction?: string | null
  entry?: string | number | null
  stop?: string | number | null
  target?: string | number | null
  confidence?: string | null
  rvol?: string | number | null
  lastClose?: string | number | null
  rsi?: string | number | null
  atr?: string | number | null
  score?: string | number | null
  hasSetup?: boolean
  narrative?: string | null
  error?: string | null
}

type Props = {
  baseUrl: string
  leftSymbol?: string
  rightSymbol?: string
  formatPrice: (value: string | number | null | undefined) => string
  onOpenResearch?: (symbol: string) => void
  embedded?: boolean
}

function confidenceFromScore(score: string | number | null | undefined): string {
  const n = Number(score)
  if (!Number.isFinite(n)) return '—'
  if (n >= 75) return 'High'
  if (n >= 55) return 'Medium'
  return 'Low'
}

function indicatorValue(
  indicators: Array<{ name: string; value?: string | number | null }> | undefined,
  pattern: RegExp,
): string | number | null {
  const hit = indicators?.find((i) => pattern.test(i.name))
  return hit?.value ?? null
}

function formatRatio(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  return `${n.toFixed(2)}x`
}

async function loadSide(baseUrl: string, symbol: string): Promise<CompareSide> {
  const sym = symbol.trim().toUpperCase()
  const empty: CompareSide = { symbol: sym || '—' }
  if (!sym) return empty

  const end = new Date()
  const start = new Date(Date.now() - 180 * 86400000)
  const startIso = start.toISOString()
  const endIso = end.toISOString()

  const [techRes, evalRes] = await Promise.all([
    fetch(`${baseUrl}/api/v1/research/${encodeURIComponent(sym)}/technical`),
    fetch(`${baseUrl}/api/v1/strategy/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: sym,
        timeframe: '1d',
        start: startIso.slice(0, 10),
        end: endIso.slice(0, 10),
      }),
    }),
  ])

  const side: CompareSide = { symbol: sym, hasSetup: false }

  if (techRes.ok) {
    const tech = (await techRes.json()) as {
      last_close?: string | number | null
      atr?: string | number | null
      volume_vs_sma?: string | number | null
      swing_fit?: string | null
      fit?: string | null
      indicators?: Array<{ name: string; value?: string | number | null }>
    }
    side.lastClose = tech.last_close ?? null
    side.atr = tech.atr ?? indicatorValue(tech.indicators, /^ATR/i)
    side.rsi = indicatorValue(tech.indicators, /^RSI/i)
    side.rvol =
      tech.volume_vs_sma ??
      indicatorValue(tech.indicators, /volume\s*vs|rvol|relative.?vol/i)
    side.confidence = tech.swing_fit || tech.fit || null
  } else {
    side.error = `Technical lookup failed (${techRes.status})`
  }

  if (evalRes.ok) {
    const body = (await evalRes.json()) as {
      has_setup?: boolean
      candidate?: {
        direction?: string
        entry_price?: string | number
        stop_loss?: string | number
        target?: string | number
        quality_score?: string | number
      }
      evidence?: { relative_volume?: string | number | null }
      reason?: string | null
      status?: string | null
    }
    if (body.has_setup && body.candidate) {
      side.hasSetup = true
      side.direction = body.candidate.direction
      side.entry = body.candidate.entry_price
      side.stop = body.candidate.stop_loss
      side.target = body.candidate.target
      side.score = body.candidate.quality_score
      side.confidence = confidenceFromScore(body.candidate.quality_score) || side.confidence
      if (body.evidence?.relative_volume != null) side.rvol = body.evidence.relative_volume
      side.narrative = null
    } else {
      side.hasSetup = false
      side.direction = null
      side.narrative = body.reason || body.status || 'No confirmed setup on latest bar'
    }
  } else if (!side.error) {
    let detail = `Strategy evaluate failed (${evalRes.status})`
    try {
      const payload = (await evalRes.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') detail = payload.detail
    } catch {
      /* keep status text */
    }
    side.error = detail
    side.narrative = detail
  }

  return side
}

function SideCard({
  side,
  formatPrice,
  onOpenResearch,
}: {
  side: CompareSide
  formatPrice: Props['formatPrice']
  onOpenResearch?: Props['onOpenResearch']
}) {
  return (
    <article className={`compare-card${side.hasSetup ? ' has-setup' : ''}`}>
      <header className="compare-card-head">
        <h3>{side.symbol}</h3>
        {onOpenResearch ? (
          <button type="button" className="ghost-btn" onClick={() => onOpenResearch(side.symbol)}>
            Open research
          </button>
        ) : null}
      </header>
      <dl className="compare-dl">
        <div>
          <dt>Last close</dt>
          <dd className="compare-value">{formatPrice(side.lastClose)}</dd>
        </div>
        <div>
          <dt>Direction</dt>
          <dd className="compare-value">
            {side.direction ? directionLabel(side.direction) : '—'}
          </dd>
        </div>
        <div>
          <dt>Entry</dt>
          <dd className="compare-value">{formatPrice(side.entry)}</dd>
        </div>
        <div>
          <dt>Stop</dt>
          <dd className="compare-value">{formatPrice(side.stop)}</dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd className="compare-value">{formatPrice(side.target)}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd className="compare-value">{side.confidence || '—'}</dd>
        </div>
        <div>
          <dt>Vol vs SMA</dt>
          <dd className="compare-value">{formatRatio(side.rvol)}</dd>
        </div>
        <div>
          <dt>RSI(14)</dt>
          <dd className="compare-value">
            {side.rsi != null && side.rsi !== '' ? Number(side.rsi).toFixed(2) : '—'}
          </dd>
        </div>
        <div>
          <dt>ATR(14)</dt>
          <dd className="compare-value">{formatPrice(side.atr)}</dd>
        </div>
      </dl>
      {side.narrative ? (
        <p className={`field-hint compare-status${side.hasSetup ? '' : ' is-muted'}`}>{side.narrative}</p>
      ) : null}
      {side.error && !side.narrative ? <p className="field-hint compare-status is-error">{side.error}</p> : null}
    </article>
  )
}

/** UC-F10 — side-by-side grounded fields only. */
export function CompareNamesDesk({
  baseUrl,
  leftSymbol = 'RELIANCE',
  rightSymbol = 'TCS',
  formatPrice,
  onOpenResearch,
  embedded = false,
}: Props) {
  const [leftInput, setLeftInput] = useState(leftSymbol)
  const [rightInput, setRightInput] = useState(rightSymbol)
  const [left, setLeft] = useState<CompareSide>({ symbol: leftSymbol })
  const [right, setRight] = useState<CompareSide>({ symbol: rightSymbol })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canRun = useMemo(
    () => leftInput.trim().length >= 1 && rightInput.trim().length >= 1,
    [leftInput, rightInput],
  )

  async function runCompare(a = leftInput, b = rightInput) {
    if (!a.trim() || !b.trim()) return
    setLoading(true)
    setError('')
    try {
      const [l, r] = await Promise.all([loadSide(baseUrl, a), loadSide(baseUrl, b)])
      setLeft(l)
      setRight(r)
      if (l.error && r.error) {
        setError('Both sides failed to load grounded data. Check API / market data.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Compare failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLeftInput(leftSymbol)
    setRightInput(rightSymbol)
    void runCompare(leftSymbol, rightSymbol)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync when parent pair changes
  }, [baseUrl, leftSymbol, rightSymbol])

  return (
    <section
      className={`${embedded ? 'compare-desk is-embedded' : 'panel compare-desk wireframe-compare'}`}
      aria-label="Compare two names"
    >
      {!embedded ? (
        <header className="header-block">
          <p className="eyebrow practice-book-brandline">
            <span className="practice-ico practice-ico-plane" aria-hidden="true" />
            <span>TradePilot</span>
            <span className="practice-brand-sep" aria-hidden="true" />
            <span>Symbol workspace</span>
          </p>
          <h1>Compare two names</h1>
          <p className="header-copy">Grounded fields only — engine levels and indicators, no fabricated peers.</p>
        </header>
      ) : (
        <header className="compare-embedded-head">
          <h2>Compare two names</h2>
          <p className="header-copy">Grounded fields only — engine levels and indicators, no fabricated peers.</p>
        </header>
      )}

      <div className="compare-controls">
        <label className="field">
          <span>Left symbol</span>
          <input value={leftInput} onChange={(e) => setLeftInput(e.target.value.toUpperCase())} />
        </label>
        <label className="field">
          <span>Right symbol</span>
          <input value={rightInput} onChange={(e) => setRightInput(e.target.value.toUpperCase())} />
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!canRun || loading}
          onClick={() => void runCompare()}
        >
          {loading ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {error ? <div className="status error">{error}</div> : null}

      <div className="compare-grid">
        <SideCard side={left} formatPrice={formatPrice} onOpenResearch={onOpenResearch} />
        <SideCard side={right} formatPrice={formatPrice} onOpenResearch={onOpenResearch} />
      </div>

      <div className="compare-peer-note" role="note">
        No fabricated peer metrics. Entry / Stop / Target appear only when the engine confirms a setup.
      </div>
      <p className="compare-disclaimer">Disclaimer: Grounded fields only. Do not use for trading decisions.</p>
    </section>
  )
}
