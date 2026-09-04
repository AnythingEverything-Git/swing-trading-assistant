/** Step-by-step beginner explanations for how TradePilot sets a trade plan. */

import { directionLabel } from './terminology'

export type DeductionStep = {
  id: string
  title: string
  value: string
  summary: string
  details: string[]
}

type DeductionInput = {
  symbol: string
  direction: string
  entry: string | number
  stop: string | number
  target: string | number
  riskPerShare: string | number
  reward: string | number
  riskRewardRatio: string | number
  setupName: string
  resistance: string | number
  retestExtreme: string | number
  atr: string | number
  breakoutVolume: number | null
  confirmationVolume: number | null
  volumeSma: string | number
  decision: string
  structureLabel?: string | null
  retestLabel?: string | null
  qualityScore?: string | number | null
  qualityReason?: string | null
  quantity?: number | null
  riskAmount?: string | number | null
  accountEquity: string
  riskPercent: string
  formatPrice: (value: string | number | null | undefined) => string
  formatNumber: (value: string | number | null | undefined, digits?: number) => string
  formatPercent: (value: string | number | null | undefined) => string
  formatRatio: (value: string | number | null | undefined) => string
}

function num(value: string | number | null | undefined): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : NaN
}

function qualityParts(input: DeductionInput) {
  const volumeSma = Math.max(num(input.volumeSma), 1)
  const breakoutVol = Number(input.breakoutVolume ?? 0)
  const confirmVol = Number(input.confirmationVolume ?? 0)
  const atr = Math.max(num(input.atr), 1e-9)
  const isShort = input.direction === 'SHORT'
  const structure = num(input.resistance)
  const retest = num(input.retestExtreme)
  const retestDistance = isShort ? retest - structure : structure - retest
  const volumeThrust = breakoutVol / volumeSma
  const confirmationRatio = confirmVol / volumeSma
  const retestTightness = Math.max(0, Math.min(3, retestDistance / atr))
  const entry = num(input.entry)
  const riskPerShare = num(input.riskPerShare)
  const riskPercentOfPrice = entry > 0 ? (riskPerShare / entry) * 100 : 0

  const volumePoints = Math.max(0, Math.min(30, (volumeThrust / 3) * 30))
  const confirmationPoints = Math.max(0, Math.min(25, (confirmationRatio / 2.5) * 25))
  const tightnessPoints = Math.max(0, Math.min(25, (1 - retestTightness / 3) * 25))
  const riskPoints = Math.max(0, Math.min(20, ((5 - riskPercentOfPrice) / 5) * 20))

  return {
    volumeThrust,
    confirmationRatio,
    retestTightness,
    riskPercentOfPrice,
    volumePoints,
    confirmationPoints,
    tightnessPoints,
    riskPoints,
    structureWord: isShort ? 'support (floor)' : 'resistance (ceiling)',
  }
}

/** Build ordered deduction steps a beginner can follow. */
export function buildPlanDeductionSteps(input: DeductionInput): DeductionStep[] {
  const isShort = input.direction === 'SHORT'
  const entry = num(input.entry)
  const stop = num(input.stop)
  const target = num(input.target)
  const risk = Math.abs(entry - stop)
  const reward = Math.abs(target - entry)
  const atr = num(input.atr)
  const structure = num(input.resistance)
  const retest = num(input.retestExtreme)
  const atrStop = isShort ? structure + atr : structure - atr
  const q = qualityParts(input)
  const equity = num(input.accountEquity)
  const riskPct = num(input.riskPercent)
  const maxRiskRupees = equity > 0 && riskPct > 0 ? (equity * riskPct) / 100 : NaN
  const structureLabel =
    input.structureLabel || (isShort ? 'Floor (support)' : 'Ceiling (resistance)')
  const retestLabel = input.retestLabel || (isShort ? 'Retest high' : 'Retest low')

  const steps: DeductionStep[] = [
    {
      id: 'trade-type',
      title: '1. Trade type',
      value: directionLabel(input.direction),
      summary: isShort
        ? 'We sell short because price broke down through support, came back to retest, then confirmed lower.'
        : 'We buy because price broke out above resistance, came back to retest, then confirmed higher.',
      details: [
        `Setup rule: ${input.setupName || 'BreakoutRetestConfirmation'}.`,
        `Decision from the scan: ${input.decision || 'confirmed pattern on the latest candle'}.`,
        isShort
          ? 'Direction = SHORT → expect the price to fall from here.'
          : 'Direction = LONG → expect the price to rise from here.',
      ],
    },
    {
      id: 'entry',
      title: '2. Buy/sell at (entry)',
      value: input.formatPrice(input.entry),
      summary:
        'Entry is the close of the confirmation candle — the last bar that finished the 3-step pattern.',
      details: [
        'Step A: Spot a clear ceiling (resistance) or floor (support) from earlier swing highs/lows.',
        isShort
          ? 'Step B: Price breaks down below that floor with strong volume.'
          : 'Step B: Price breaks out above that ceiling with strong volume.',
        'Step C: Price retests the broken level (comes back to “test” it).',
        'Step D: The newest candle confirms the move — we take its close as buy/sell at.',
        `${structureLabel}: ${input.formatPrice(input.resistance)}.`,
        `${retestLabel}: ${input.formatPrice(input.retestExtreme)}.`,
      ],
    },
    {
      id: 'stop',
      title: '3. Safety exit (stop)',
      value: input.formatPrice(input.stop),
      summary: isShort
        ? 'Stop sits above entry — if price rises against us, we exit to limit the loss.'
        : 'Stop sits below entry — if price falls against us, we exit to limit the loss.',
      details: [
        `ATR (14-day volatility) near the retest ≈ ${input.formatNumber(input.atr, 2)}.`,
        isShort
          ? `ATR-based stop candidate = floor + ATR = ${input.formatPrice(structure)} + ${input.formatNumber(atr, 2)} ≈ ${input.formatPrice(atrStop)}.`
          : `ATR-based stop candidate = ceiling − ATR = ${input.formatPrice(structure)} − ${input.formatNumber(atr, 2)} ≈ ${input.formatPrice(atrStop)}.`,
        isShort
          ? `Retest-based stop candidate = retest high = ${input.formatPrice(retest)}.`
          : `Retest-based stop candidate = retest low = ${input.formatPrice(retest)}.`,
        isShort
          ? `We pick the safer (higher) of those two → stop = ${input.formatPrice(stop)}.`
          : `We pick the safer (lower) of those two → stop = ${input.formatPrice(stop)}.`,
        `Risk per share = |entry − stop| = |${input.formatPrice(entry)} − ${input.formatPrice(stop)}| = ${input.formatPrice(risk)}.`,
        'Rule: risk per share must stay within 5% of the entry price, or the setup is rejected.',
      ],
    },
    {
      id: 'target',
      title: '4. Profit goal (target)',
      value: input.formatPrice(input.target),
      summary: 'Profit goal is always set at 2× the risk distance (2R).',
      details: [
        `Risk (1R) = ${input.formatPrice(risk)} per share.`,
        isShort
          ? `Target = entry − 2 × risk = ${input.formatPrice(entry)} − 2 × ${input.formatPrice(risk)} = ${input.formatPrice(target)}.`
          : `Target = entry + 2 × risk = ${input.formatPrice(entry)} + 2 × ${input.formatPrice(risk)} = ${input.formatPrice(target)}.`,
        `Reward per share = |target − entry| = ${input.formatPrice(reward)}.`,
      ],
    },
    {
      id: 'rr',
      title: '5. Reward vs risk',
      value: input.formatRatio(input.riskRewardRatio),
      summary: 'This ratio asks: for every ₹1 we risk, how many rupees can we aim to make?',
      details: [
        `Reward ÷ risk = ${input.formatPrice(reward)} ÷ ${input.formatPrice(risk)} ≈ ${input.formatRatio(input.riskRewardRatio)}.`,
        'TradePilot requires about 2.00x — if the math cannot reach 2R with a valid stop, the idea is discarded.',
      ],
    },
    {
      id: 'quality',
      title: '6. Quality score',
      value: input.qualityScore == null ? '—' : input.formatNumber(input.qualityScore, 1),
      summary: 'A 0–100 score that ranks how “clean” the setup looks — higher is better.',
      details: [
        `Volume thrust (breakout volume ÷ volume SMA) ≈ ${input.formatNumber(q.volumeThrust, 2)}x → up to 30 points (here ≈ ${input.formatNumber(q.volumePoints, 1)}).`,
        `Confirmation volume ÷ SMA ≈ ${input.formatNumber(q.confirmationRatio, 2)}x → up to 25 points (here ≈ ${input.formatNumber(q.confirmationPoints, 1)}).`,
        `Retest tightness ≈ ${input.formatNumber(q.retestTightness, 2)} ATR from ${q.structureWord} → up to 25 points (tighter is better; here ≈ ${input.formatNumber(q.tightnessPoints, 1)}).`,
        `Stop size as % of price ≈ ${input.formatPercent(q.riskPercentOfPrice)} → up to 20 points (smaller risk % is better; here ≈ ${input.formatNumber(q.riskPoints, 1)}).`,
        input.qualityReason
          ? `Scanner note: ${input.qualityReason}`
          : 'These four parts are added for the final quality score used in ranking.',
      ],
    },
    {
      id: 'shares',
      title: '7. Shares quantity',
      value: input.quantity == null ? '—' : String(input.quantity),
      summary: 'Share count comes from your capital and risk %, not from guessing a round lot.',
      details: [
        `Your capital (from the form) = ${input.formatPrice(equity)}.`,
        `Risk % you chose = ${input.formatPercent(riskPct)}.`,
        Number.isFinite(maxRiskRupees)
          ? `Max rupees you are willing to lose on this idea = capital × risk% = ${input.formatPrice(maxRiskRupees)}.`
          : 'Set capital and risk % on Find setups to size shares.',
        `Risk per share = ${input.formatPrice(input.riskPerShare)}.`,
        Number.isFinite(maxRiskRupees) && num(input.riskPerShare) > 0
          ? `Shares = floor(max risk ÷ risk per share) = floor(${input.formatPrice(maxRiskRupees)} ÷ ${input.formatPrice(input.riskPerShare)}) = ${input.quantity ?? 0}.`
          : 'Shares cannot be computed until capital, risk %, and risk per share are available.',
        input.riskAmount != null
          ? `Actual rupees at risk with that share count ≈ ${input.formatPrice(input.riskAmount)}.`
          : 'If shares = 0, the stop is too wide for your risk budget — skip or raise capital/risk %.',
      ],
    },
  ]

  return steps
}
