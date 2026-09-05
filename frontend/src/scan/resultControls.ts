/** Client-side sort/filter for ranked eligible + forming scan results. */

import type { FormingSetup, Opportunity } from './types'

export type SortDir = 'asc' | 'desc'
export type ResultSortKey = 'rank' | 'confidence' | 'rr' | 'change' | 'symbol'
export type DirectionFilter = 'ALL' | 'LONG' | 'SHORT'
export type FormingSortKey = 'symbol' | 'change' | 'bars' | 'stage' | 'direction'
export type FormingStageFilter = 'ALL' | 'AWAITING_RETEST' | 'AWAITING_CONFIRMATION'

export type ResultControls = {
  sortBy: ResultSortKey
  sortDir: SortDir
  direction: DirectionFilter
  minConfidence: string
  minRr: string
}

export type FormingControls = {
  sortBy: FormingSortKey
  sortDir: SortDir
  direction: DirectionFilter
  stage: FormingStageFilter
}

export const DEFAULT_RESULT_CONTROLS: ResultControls = {
  sortBy: 'rank',
  sortDir: 'asc',
  direction: 'ALL',
  minConfidence: '',
  minRr: '',
}

export const DEFAULT_FORMING_CONTROLS: FormingControls = {
  sortBy: 'bars',
  sortDir: 'asc',
  direction: 'ALL',
  stage: 'ALL',
}

/** Map rules-based quality score (0–100) to strategy confidence %. */
export function strategyConfidencePercent(
  qualityScore: string | number | null | undefined,
): number | null {
  if (qualityScore == null || qualityScore === '') return null
  const numeric = Number(qualityScore)
  if (!Number.isFinite(numeric)) return null
  return Math.max(0, Math.min(100, Math.round(numeric)))
}

function num(value: string | number | null | undefined): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : Number.NaN
}

function applyDir(diff: number, dir: SortDir): number {
  if (!Number.isFinite(diff) || diff === 0) return 0
  return dir === 'asc' ? diff : -diff
}

/** Toggle sort: same key flips direction; new key starts at a sensible default. */
export function nextSortState<K extends string>(
  currentKey: K,
  currentDir: SortDir,
  nextKey: K,
  defaultDir: SortDir = 'desc',
): { sortBy: K; sortDir: SortDir } {
  if (currentKey === nextKey) {
    return { sortBy: nextKey, sortDir: currentDir === 'asc' ? 'desc' : 'asc' }
  }
  return { sortBy: nextKey, sortDir: defaultDir }
}

export function filterAndSortOpportunities(
  opportunities: Opportunity[],
  controls: ResultControls,
): Opportunity[] {
  const minConf = controls.minConfidence.trim() === '' ? null : Number(controls.minConfidence)
  const minRr = controls.minRr.trim() === '' ? null : Number(controls.minRr)

  const rows = opportunities.filter((item) => {
    if (controls.direction === 'LONG' && item.candidate.direction !== 'LONG') return false
    if (controls.direction === 'SHORT' && item.candidate.direction !== 'SHORT') return false
    if (minConf != null && Number.isFinite(minConf)) {
      const conf = strategyConfidencePercent(item.quality_score)
      if (conf == null || conf < minConf) return false
    }
    if (minRr != null && Number.isFinite(minRr)) {
      const rr = num(item.candidate.risk_reward_ratio)
      if (!Number.isFinite(rr) || rr < minRr) return false
    }
    return true
  })

  const sorted = [...rows]
  sorted.sort((a, b) => {
    let diff = 0
    switch (controls.sortBy) {
      case 'rr':
        diff = num(a.candidate.risk_reward_ratio) - num(b.candidate.risk_reward_ratio)
        break
      case 'change':
        diff = num(a.current_price_change_percent) - num(b.current_price_change_percent)
        break
      case 'symbol':
        diff = a.symbol.localeCompare(b.symbol)
        break
      case 'confidence':
        diff = num(a.quality_score) - num(b.quality_score)
        break
      case 'rank':
      default:
        diff = (a.rank ?? 9999) - (b.rank ?? 9999)
        break
    }
    const primary = applyDir(diff, controls.sortDir)
    if (primary !== 0) return primary
    const rankA = a.rank ?? Number.MAX_SAFE_INTEGER
    const rankB = b.rank ?? Number.MAX_SAFE_INTEGER
    if (rankA !== rankB) return rankA - rankB
    return a.symbol.localeCompare(b.symbol)
  })
  return sorted
}

export function filterAndSortForming(
  forming: FormingSetup[],
  controls: FormingControls,
): FormingSetup[] {
  const rows = forming.filter((item) => {
    const direction = item.direction ?? 'LONG'
    if (controls.direction === 'LONG' && direction !== 'LONG') return false
    if (controls.direction === 'SHORT' && direction !== 'SHORT') return false
    if (controls.stage !== 'ALL' && item.stage !== controls.stage) return false
    return true
  })

  const sorted = [...rows]
  sorted.sort((a, b) => {
    let diff = 0
    switch (controls.sortBy) {
      case 'change':
        diff = num(a.current_price_change_percent) - num(b.current_price_change_percent)
        break
      case 'bars':
        diff = a.bars_remaining - b.bars_remaining
        break
      case 'stage':
        diff = a.stage.localeCompare(b.stage)
        break
      case 'direction':
        diff = (a.direction ?? 'LONG').localeCompare(b.direction ?? 'LONG')
        break
      case 'symbol':
      default:
        diff = a.symbol.localeCompare(b.symbol)
        break
    }
    const primary = applyDir(diff, controls.sortDir)
    if (primary !== 0) return primary
    return a.symbol.localeCompare(b.symbol)
  })
  return sorted
}
