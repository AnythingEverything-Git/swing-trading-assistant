/** Deterministic backtest interpreter bullets — never invents trades or retunes V1. */

export type BacktestMetricsLike = {
  win_rate?: string | number | null
  total_trades?: number | null
  average_r?: string | number | null
  maximum_drawdown?: string | number | null
  total_pnl?: string | number | null
}

function pct(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  const asPct = Math.abs(n) <= 1 ? n * 100 : n
  return `${asPct.toFixed(1)}%`
}

export function buildBacktestInterpreter(
  symbol: string,
  metrics: BacktestMetricsLike | null | undefined,
  existingNarrative?: string | null,
): { bullets: string[]; refused: string } {
  const refused = 'Refuse: Retune V1 to make profitable'
  if (!metrics) {
    return {
      bullets: [
        `${symbol} backtest parameters analyzed.`,
        'Simulated historical data reviewed.',
        'Never invents trades.',
      ],
      refused,
    }
  }

  const trades = Number(metrics.total_trades) || 0
  const win = pct(metrics.win_rate)
  const dd = pct(metrics.maximum_drawdown)
  const sampleNote =
    trades >= 100
      ? 'Sample size is adequate for a first read.'
      : trades >= 30
        ? 'Sample size is moderate — treat stats carefully.'
        : 'Sample size is small — do not over-read the win rate.'

  const bullets = [
    `Win rate: ${win} based on ${trades} trade${trades === 1 ? '' : 's'}.`,
    `Max drawdown: ${dd}.`,
    sampleNote,
    `${symbol} backtest parameters analyzed.`,
    'Never invents trades.',
  ]

  if (existingNarrative?.trim()) {
    const first = existingNarrative
      .split(/(?<=[.!?])\s+|\n+/)
      .map((p) => p.trim())
      .find(Boolean)
    if (first && !bullets.some((b) => b.includes(first.slice(0, 24)))) {
      bullets.splice(3, 0, first)
    }
  }

  return { bullets: bullets.slice(0, 6), refused }
}
