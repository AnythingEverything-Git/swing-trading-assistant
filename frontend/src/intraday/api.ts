/** Intraday ORB session API client. */

export type IntradaySymbolResult = {
  symbol: string
  reason: string
  rank: number | null
  rvol5: string | null
  direction: string | null
  detail: string | null
  asset_class?: 'STOCK' | 'ETF' | null
}

export type IntradayRankedRow = {
  rank: number | null
  symbol: string
  asset_class: string
  direction: string | null
  rvol5: string | null
  or_high?: string | null
  or_low?: string | null
  or_expansion_pct?: string | null
  adv_value?: string | null
  adv_band?: string | null
  short_allowed?: boolean
  surveillance_blocked?: boolean
  corporate_action_blocked?: boolean
  corporate_action_label?: string | null
  adv_ok?: boolean
  status?: string
  detail?: string | null
}

export type MorningBoardResponse = {
  session_date: string
  strategy_id: string
  config_hash: string
  phase: 'PRE_OPEN' | 'OR_BUILDING' | 'LIVE_SCREEN' | 'HISTORICAL'
  phase_label: string
  auto_refresh_seconds: number
  claim: string
  universe_stocks: number
  universe_etfs: number
  ranked_stocks: IntradayRankedRow[]
  ranked_etfs: IntradayRankedRow[]
  eligible_stocks?: IntradayRankedRow[]
  eligible_etfs?: IntradayRankedRow[]
  blocked_sample?: Array<{
    symbol: string
    asset_class: string
    reason: string
    detail: string | null
    rvol5: string | null
    direction: string | null
  }>
  reason_counts: Record<string, number>
  coverage: Record<string, unknown>
  hint: string
}

export type IntradayFill = {
  symbol: string
  direction: string
  rank: number
  entry: string
  stop: string
  quantity: number
  trigger_bar_open: string
  stop_distance?: string | null
  risk_amount?: string | null
  effective_risk_per_share?: string | null
}

export type IntradayClosedTrade = {
  symbol: string
  direction: string
  entry: string
  exit: string
  exit_reason: string
  pnl: string
  exit_time: string
  quantity?: number | null
  stop?: string | null
  mfe?: string | null
  mae?: string | null
  giveback?: string | null
  entry_time?: string | null
}

export type IntradaySessionResponse = {
  id: string
  session_date: string
  strategy_id: string
  config_hash: string
  coverage_eligible: number
  coverage_total: number
  coverage_pct?: number
  reason_counts?: Record<string, number>
  ranked_stocks?: IntradayRankedRow[]
  ranked_etfs?: IntradayRankedRow[]
  symbol_results: IntradaySymbolResult[]
  fills: IntradayFill[]
  closed_trades: IntradayClosedTrade[]
  created_at?: string
  data_source?: string
  coverage_detail?: Record<string, unknown>
}

export type IntradayUniverse =
  | 'DEMO_SAMPLE'
  | 'NIFTY_50'
  | 'NIFTY_100'
  | 'NIFTY_200'
  | 'NIFTY_500'
  | 'NSE_ETF'
  | 'NSE_CASH'
  | 'NSE_ALL'
  | 'NSE_MORNING'
  | 'CUSTOM'

export type IntradaySessionRunRequest = {
  session_date?: string | null
  symbols?: string[] | null
  universe?: Exclude<IntradayUniverse, 'CUSTOM'> | null
  equity?: string
  source?: 'demo' | 'persisted'
}

function detailFromErrorPayload(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const record = payload as { detail?: unknown; message?: unknown }
    if (typeof record.detail === 'string') return record.detail
    if (Array.isArray(record.detail) && record.detail.length > 0) {
      const first = record.detail[0] as { msg?: unknown; loc?: unknown }
      if (typeof first?.msg === 'string') {
        const loc = Array.isArray(first.loc) ? first.loc.join('.') : ''
        return loc ? `${loc}: ${first.msg}` : first.msg
      }
    }
    if (typeof record.message === 'string') return record.message
  }
  return fallback
}

export type IntradaySessionSummary = {
  id: string
  created_at: string
  session_date: string
  strategy_id: string
  config_hash: string
  data_source: string
  coverage_eligible: number
  coverage_total: number
  fill_count: number
  realized_pnl: string | null
}

export async function runIntradaySession(
  baseUrl: string,
  body: IntradaySessionRunRequest,
): Promise<IntradaySessionResponse> {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = 'Intraday session failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as IntradaySessionResponse
}

export async function getIntradaySession(
  baseUrl: string,
  sessionId: string,
): Promise<IntradaySessionResponse> {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/${sessionId}`)
  if (!response.ok) {
    let detail = 'Failed to load intraday session'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as IntradaySessionResponse
}

export async function listIntradaySessions(
  baseUrl: string,
  limit = 10,
): Promise<{ sessions: IntradaySessionSummary[] }> {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions?limit=${limit}`)
  if (!response.ok) {
    let detail = 'Failed to list intraday sessions'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as { sessions: IntradaySessionSummary[] }
}

export type IntradayChartResponse = {
  session_id: string
  symbol: string
  session_date: string
  data_source: string
  timeframe: string
  direction: string | null
  reason: string | null
  or_open: string | null
  or_high: string | null
  or_low: string | null
  entry: string | null
  stop: string | null
  exit: string | null
  trigger_index: number | null
  candles: Array<{
    timestamp: string
    open: string
    high: string
    low: string
    close: string
    volume: number
  }>
}

export async function getIntradaySessionChart(
  baseUrl: string,
  sessionId: string,
  symbol: string,
  timeframe: '1m' | '5m' = '1m',
): Promise<IntradayChartResponse> {
  const response = await fetch(
    `${baseUrl}/api/v1/intraday/sessions/${sessionId}/chart/${encodeURIComponent(symbol)}?timeframe=${timeframe}`,
  )
  if (!response.ok) {
    let detail = 'Failed to load chart'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as IntradayChartResponse
}

export type IntradayPracticeTrade = {
  id: number
  session_id: string
  session_date: string
  symbol: string
  direction: string
  entry_price: string
  stop_loss: string
  quantity: number
  risk_amount: string | null
  status: string
  opened_at: string | null
  closed_at: string | null
  exit_price: string | null
  exit_reason: string | null
  last_mark_price: string | null
  unrealized_pnl: string | null
  realized_pnl: string | null
}

export async function seedIntradayPractice(baseUrl: string, sessionId: string) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/${sessionId}/practice/seed`, {
    method: 'POST',
  })
  if (!response.ok) {
    let detail = 'Failed to seed practice trades'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as {
    opened: number
    skipped: number
    claim: string
    trades: IntradayPracticeTrade[]
  }
}

export async function listIntradayPractice(baseUrl: string, sessionId: string) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/${sessionId}/practice`)
  if (!response.ok) {
    let detail = 'Failed to load practice trades'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as { session_id: string; trades: IntradayPracticeTrade[]; claim: string }
}

export async function tickIntradayPractice(
  baseUrl: string,
  sessionId: string,
  body?: { marks?: Record<string, string>; force_eod?: boolean; use_live_quotes?: boolean },
) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/${sessionId}/practice/tick`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_live_quotes: true, ...body }),
  })
  if (!response.ok) {
    let detail = 'Practice tick failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as {
    marks_applied: number
    closed_this_tick: IntradayPracticeTrade[]
    open_count: number
    quote_source?: string
    claim: string
  }
}

export async function fetchMorningBoard(
  baseUrl: string,
  params: {
    session_date?: string | null
    source?: 'demo' | 'persisted'
    equity?: string
    universe?: string
    symbols?: string[]
    filters?: Record<string, unknown>
  } = {},
): Promise<MorningBoardResponse> {
  if (params.filters || params.universe || params.symbols) {
    const response = await fetch(`${baseUrl}/api/v1/intraday/morning-board`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_date: params.session_date || null,
        source: params.source || 'demo',
        equity: params.equity || '1000000',
        universe: params.universe || 'NSE_ALL',
        symbols: params.symbols || null,
        filters: params.filters || {},
      }),
    })
    if (!response.ok) {
      let detail = 'Morning board failed'
      try {
        detail = detailFromErrorPayload(await response.json(), detail)
      } catch {
        detail = response.statusText || detail
      }
      throw new Error(detail)
    }
    return (await response.json()) as MorningBoardResponse
  }
  const qs = new URLSearchParams()
  if (params.session_date) qs.set('session_date', params.session_date)
  if (params.source) qs.set('source', params.source)
  if (params.equity) qs.set('equity', params.equity)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const response = await fetch(`${baseUrl}/api/v1/intraday/morning-board${suffix}`)
  if (!response.ok) {
    let detail = 'Morning board failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as MorningBoardResponse
}

export async function ensure1mActiveSet(
  baseUrl: string,
  symbols: string[],
): Promise<{ ok: boolean; detail?: string }> {
  const response = await fetch(`${baseUrl}/api/v1/intraday/ingest/ensure-1m`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbols }),
  })
  if (!response.ok) {
    let detail = 'ensure-1m failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    return { ok: false, detail }
  }
  return { ok: true }
}

export async function runMorningIntradaySession(
  baseUrl: string,
  body: {
    universe?: Exclude<IntradayUniverse, 'CUSTOM'>
    symbols?: string[] | null
    equity?: string
    source?: 'demo' | 'persisted'
    seed_practice?: boolean
    session_date?: string | null
  },
) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/morning`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = 'Morning session failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as {
    session: IntradaySessionResponse
    practice: { opened: number; skipped: number; claim: string; trades: IntradayPracticeTrade[] } | null
    hint: string
  }
}

export async function getPracticeDivergence(baseUrl: string, sessionId: string) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/${sessionId}/practice/divergence`)
  if (!response.ok) {
    let detail = 'Divergence check failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as {
    session_id: string
    matched_closed: number
    total_practice: number
    total_model_closed: number
    pnl_gap_sum: string
    rows: Array<{
      symbol: string
      practice_status: string
      model_status: string
      practice_pnl: string | null
      model_pnl: string | null
      pnl_gap: string | null
      exit_match: boolean
    }>
    note: string
  }
}

export async function reconcilePractice(baseUrl: string, sessionId: string) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/${sessionId}/practice/reconcile`)
  if (!response.ok) {
    let detail = 'Reconcile failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as {
    session_id?: string
    trading_halted: boolean
    issue_count: number
    issues: Array<{ symbol: string; code: string; detail: string }>
    note?: string
    claim?: string
  }
}

export async function closePracticeTrade(baseUrl: string, tradeId: number, price: string) {
  const response = await fetch(`${baseUrl}/api/v1/intraday/practice/${tradeId}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price }),
  })
  if (!response.ok) {
    let detail = 'Close practice failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return (await response.json()) as IntradayPracticeTrade
}
