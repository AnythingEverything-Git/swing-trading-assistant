/** Intraday ORB session API client. */

export type IntradayDecision = 'EXECUTE' | 'WATCH' | 'REJECT'

export type IntradaySymbolResult = {
  symbol: string
  reason: string
  rank: number | null
  rvol5: string | null
  direction: string | null
  detail: string | null
  asset_class?: 'STOCK' | 'ETF' | null
  decision?: IntradayDecision | null
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
  current_price?: string | null
  entry?: string | null
  stop?: string | null
  target?: string | null
  target_label?: string | null
  quantity?: number | null
  risk_amount?: string | null
  size_status?: string | null
  reason?: string | null
  stop_distance?: string | null
  effective_risk_per_share?: string | null
  decision?: IntradayDecision | null
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
  decision_counts?: Partial<Record<'EXECUTE' | 'WATCH' | 'REJECT', number>>
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
  decision_counts?: Partial<Record<'EXECUTE' | 'WATCH' | 'REJECT', number>>
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
  max_risk_per_trade_inr?: string
  max_open_risk_inr?: string
  daily_loss_lock_inr?: string
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

async function pollSessionJob<T>(baseUrl: string, jobId: string): Promise<T> {
  const deadline = Date.now() + 180_000
  while (Date.now() < deadline) {
    const response = await fetch(
      `${baseUrl}/api/v1/intraday/sessions/jobs/${encodeURIComponent(jobId)}`,
    )
    if (!response.ok) {
      throw new Error(`Session job failed (${response.status})`)
    }
    const payload = (await response.json()) as {
      status?: string
      error?: string
      result?: T
      session_id?: string
    }
    if (payload.status === 'ready' && payload.result != null) {
      return payload.result
    }
    if (payload.status === 'failed') {
      throw new Error(payload.error || 'Session job failed')
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  throw new Error('Session job timed out')
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
  if (response.status === 202) {
    const accepted = (await response.json()) as { job_id?: string }
    if (!accepted.job_id) throw new Error('Session accepted without job_id')
    return pollSessionJob<IntradaySessionResponse>(baseUrl, accepted.job_id)
  }
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
    force_refresh?: boolean
    max_risk_per_trade_inr?: string
    max_open_risk_inr?: string
    daily_loss_lock_inr?: string
  } = {},
): Promise<MorningBoardResponse> {
  const appendRiskQs = (qs: URLSearchParams) => {
    if (params.max_risk_per_trade_inr) qs.set('max_risk_per_trade_inr', params.max_risk_per_trade_inr)
    if (params.max_open_risk_inr) qs.set('max_open_risk_inr', params.max_open_risk_inr)
    if (params.daily_loss_lock_inr) qs.set('daily_loss_lock_inr', params.daily_loss_lock_inr)
  }
  const pollJob = async (jobId: string): Promise<MorningBoardResponse> => {
    const deadline = Date.now() + 120_000
    while (Date.now() < deadline) {
      const response = await fetch(`${baseUrl}/api/v1/intraday/morning-board/jobs/${encodeURIComponent(jobId)}`)
      if (!response.ok) {
        throw new Error(`Morning board job failed (${response.status})`)
      }
      const payload = (await response.json()) as {
        status?: string
        error?: string
        job?: { status?: string; error?: string }
        board?: MorningBoardResponse
      }
      if (payload.board) return payload.board
      const status = payload.status || payload.job?.status
      if (status === 'failed') {
        throw new Error(payload.error || payload.job?.error || 'Morning board rebuild failed')
      }
      if (status === 'ready') {
        // Job finished — cache is warm; fetch the accurate board payload.
        const qs = new URLSearchParams()
        if (params.session_date) qs.set('session_date', params.session_date)
        if (params.source) qs.set('source', params.source)
        if (params.equity) qs.set('equity', params.equity)
        qs.set('universe', params.universe || 'NIFTY_500')
        appendRiskQs(qs)
        const suffix = qs.toString() ? `?${qs.toString()}` : ''
        const boardResp = await fetch(`${baseUrl}/api/v1/intraday/morning-board${suffix}`)
        if (boardResp.status === 202) {
          await new Promise((r) => setTimeout(r, 400))
          continue
        }
        if (!boardResp.ok) {
          throw new Error(`Morning board fetch failed (${boardResp.status})`)
        }
        return (await boardResp.json()) as MorningBoardResponse
      }
      await new Promise((r) => setTimeout(r, 400))
    }
    throw new Error('Morning board timed out waiting for rebuild')
  }

  const handleResponse = async (response: Response): Promise<MorningBoardResponse> => {
    if (response.status === 202) {
      const accepted = (await response.json()) as { job_id?: string }
      if (!accepted.job_id) throw new Error('Morning board accepted without job_id')
      return pollJob(accepted.job_id)
    }
    if (!response.ok) {
      let detail = 'Morning board failed'
      try {
        detail = detailFromErrorPayload(await response.json(), detail)
      } catch {
        detail = response.statusText || detail
      }
      throw new Error(detail)
    }
    const board = (await response.json()) as MorningBoardResponse & { rebuild_job_id?: string }
    return board
  }

  if (params.filters || params.universe || params.symbols || params.force_refresh) {
    const response = await fetch(`${baseUrl}/api/v1/intraday/morning-board`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_date: params.session_date || null,
        source: params.source || 'persisted',
        equity: params.equity || '1000000',
        universe: params.universe || 'NIFTY_500',
        symbols: params.symbols || null,
        filters: params.filters || {},
        force_refresh: Boolean(params.force_refresh),
        max_risk_per_trade_inr: params.max_risk_per_trade_inr || null,
        max_open_risk_inr: params.max_open_risk_inr || null,
        daily_loss_lock_inr: params.daily_loss_lock_inr || null,
      }),
    })
    return handleResponse(response)
  }
  const qs = new URLSearchParams()
  if (params.session_date) qs.set('session_date', params.session_date)
  if (params.source) qs.set('source', params.source)
  if (params.equity) qs.set('equity', params.equity)
  qs.set('universe', params.universe || 'NIFTY_500')
  appendRiskQs(qs)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const response = await fetch(`${baseUrl}/api/v1/intraday/morning-board${suffix}`)
  return handleResponse(response)
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
  // 202 = accepted background job (full accuracy ingest continues off-request)
  if (response.status !== 200 && response.status !== 202) {
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
    max_risk_per_trade_inr?: string
    max_open_risk_inr?: string
    daily_loss_lock_inr?: string
  },
) {
  type MorningResult = {
    session: IntradaySessionResponse
    practice: { opened: number; skipped: number; claim: string; trades: IntradayPracticeTrade[] } | null
    hint?: string
  }

  const response = await fetch(`${baseUrl}/api/v1/intraday/sessions/morning`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (response.status === 202) {
    const accepted = (await response.json()) as { job_id?: string }
    if (!accepted.job_id) throw new Error('Morning session accepted without job_id')
    const result = await pollSessionJob<MorningResult>(baseUrl, accepted.job_id)
    if (!result?.session?.id) {
      throw new Error('Morning session finished without a session id')
    }
    return {
      session: result.session,
      practice: result.practice ?? null,
      hint: result.hint || '',
    }
  }
  if (!response.ok) {
    let detail = 'Morning session failed'
    try {
      detail = detailFromErrorPayload(await response.json(), detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  const payload = (await response.json()) as MorningResult
  if (!payload?.session?.id) {
    throw new Error('Morning session response missing session.id')
  }
  return {
    session: payload.session,
    practice: payload.practice ?? null,
    hint: payload.hint || '',
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
