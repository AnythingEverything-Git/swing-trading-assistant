/** Step-by-step beginner explanations for ORB V1 (no profit goal / 2R). */

import { directionLabel, ORB_V1_RULES } from '../terminology'
import type { DeductionStep } from '../planDeduction'
import type { IntradayClosedTrade, IntradayFill, IntradaySymbolResult } from './api'

type FormatPrice = (value: string | number | null | undefined) => string

export function buildOrbDeductionSteps(input: {
  row: IntradaySymbolResult
  fill?: IntradayFill | null
  closed?: IntradayClosedTrade | null
  accountEquity: string
  formatPrice: FormatPrice
}): DeductionStep[] {
  const { row, fill, closed, accountEquity, formatPrice } = input
  const side = row.direction ?? fill?.direction ?? 'LONG'
  const rvol = row.rvol5 != null ? Number(row.rvol5).toFixed(2) : '—'
  const equity = Number(accountEquity)
  const riskBudget =
    Number.isFinite(equity) && equity > 0
      ? formatPrice((equity * ORB_V1_RULES.riskPerTradePct) / 100)
      : '—'

  const steps: DeductionStep[] = [
    {
      id: 'direction',
      title: 'Trade type',
      value: directionLabel(side),
      summary:
        side === 'SHORT'
          ? 'Opening range closed nearer the low → rules look for a breakdown short.'
          : 'Opening range closed nearer the high → rules look for a breakout long.',
      details: [
        `Opening range window: ${ORB_V1_RULES.orWindow} (first 5 minutes).`,
        'If the range is a doji (too tight), V1 skips the name — no direction.',
      ],
    },
    {
      id: 'screen',
      title: 'Relative volume screen',
      value: row.rank != null ? `Rank #${row.rank} · RVOL5 ${rvol}` : `RVOL5 ${rvol}`,
      summary:
        'First-5-minute volume vs the prior ~14 sessions. Higher RVOL ranks first; only Top 20 are armed.',
      details: [
        `Minimum RVOL5: ${ORB_V1_RULES.minRvol5}×`,
        `Top N armed: ${ORB_V1_RULES.topN}`,
        row.detail ? `Engine note: ${row.detail}` : 'Screen uses rules only — not a win-rate forecast.',
      ],
    },
    {
      id: 'trigger',
      title: 'Entry trigger',
      value: fill
        ? `1m breakout at ${formatPrice(fill.entry)}`
        : 'Wait for 1-minute close beyond opening range',
      summary: fill
        ? 'Price closed through the opening-range extreme on a 1-minute bar, so rules entered.'
        : 'No entry until a 1-minute close breaks the OR high (long) or OR low (short), before 14:30.',
      details: [
        `No new entries after ${ORB_V1_RULES.entryCutoff}.`,
        fill
          ? `Trigger bar: ${fill.trigger_bar_open.replace('T', ' ').slice(0, 19)} IST`
          : 'Armed names sit until breakout, cutoff, or session end.',
      ],
    },
    {
      id: 'stop',
      title: 'Safety exit',
      value: fill ? formatPrice(fill.stop) : '0.10 × prior ATR14 (bounded)',
      summary:
        'Stop is rules-based from prior-day ATR, then clipped by tick / % / OR-width bounds. There is no profit goal in V1.',
      details: [
        `ATR multiplier: ${ORB_V1_RULES.stopAtrMult}× prior ATR14`,
        fill?.stop_distance != null
          ? `Stop distance: ${formatPrice(fill.stop_distance)} per share`
          : 'Distance must clear minimum ticks and stay within OR-width bounds.',
        'Exit = hit safety exit OR forced flatten at 15:10 — never hold overnight.',
      ],
    },
    {
      id: 'sizing',
      title: 'Shares',
      value: fill ? `${fill.quantity} shares` : `Risk ≈ ${ORB_V1_RULES.riskPerTradePct}% of capital`,
      summary: fill
        ? `Sized so roughly ${ORB_V1_RULES.riskPerTradePct}% of your capital is at risk to the safety exit.`
        : `When a fill prints, shares = risk budget ÷ stop distance (capped by position and portfolio limits).`,
      details: [
        `Your capital (desk): ${formatPrice(accountEquity)}`,
        `Risk budget this trade: ~${riskBudget}`,
        fill?.risk_amount != null ? `Rules risk amount: ${formatPrice(fill.risk_amount)}` : '',
        `Max concurrent positions: ${ORB_V1_RULES.maxConcurrent}`,
      ].filter(Boolean),
    },
    {
      id: 'exit',
      title: 'How it ends',
      value: closed
        ? closed.exit_reason === 'EOD_EXIT'
          ? 'Forced flatten 15:10'
          : 'Safety exit'
        : `Safety exit or flatten by ${ORB_V1_RULES.flatten}`,
      summary: closed
        ? closed.exit_reason === 'EOD_EXIT'
          ? 'Still open near the close — V1 flats everything at 15:10 so nothing carries overnight.'
          : 'Price hit the safety exit; rules cut the trade.'
        : 'V1 never sets a profit goal. Manage with the stop, or the clock flats you.',
      details: [
        closed ? `Exit price: ${formatPrice(closed.exit)}` : `Flatten clock: ${ORB_V1_RULES.flatten}`,
        closed ? `P/L: ${formatPrice(closed.pnl)}` : 'One trade per symbol per day.',
        'AI (if used elsewhere) may rephrase wording only — it cannot change Entry / Stop / Qty.',
      ],
    },
  ]

  return steps
}
