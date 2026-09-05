/** Shared scan API types for the Find setups desk. */

export type Candidate = {
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

export type Evidence = {
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
  structure_level?: string | number | null
  retest_extreme?: string | number | null
  structure_label?: string | null
  retest_label?: string | null
}

export type Opportunity = {
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
  narrative_source?: string | null
  invalidation_source?: string | null
  quality_critique?: string | null
  quality_flags?: string[]
  volume_thrust?: string | number | null
  retest_tightness?: string | number | null
  risk_percent?: string | number | null
  confirmation_volume_ratio?: string | number | null
  current_price?: string | number | null
  current_price_change_percent?: string | number | null
}

export type FormingSetup = {
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

export type OpportunityScanResponse = {
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
  data_quality_bullets?: string[] | null
  ai_brief?: string | null
  paper_opened_count?: number
  paper_skipped_count?: number
  paper_claim?: string | null
  status?: string
  error_message?: string | null
}

export type ScanRunSummary = {
  id: number
  started_at: string
  finished_at: string | null
  universe_name: string | null
  result_count: number
  symbols_scanned: number | null
  data_source: string | null
  status?: string | null
}

export type ScanJobAccepted = {
  scan_run_id: number
  status: string
  message?: string
}

export type ScanRunStatus = {
  scan_run_id: number
  status: string
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export type StartScanRequest = {
  universe: string
  timeframe: string
  start: string
  end: string
  account_equity?: string
  risk_percent?: string
  top_n?: number
  min_score?: string
  enable_paper_trading?: boolean
}
