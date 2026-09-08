/** Shared NSE filter builder — UC-B2 modal + compact intraday variant. */

import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'

export type UniverseFilterState = {
  asset_class: 'ALL' | 'STOCK' | 'ETF'
  min_price: string
  max_price: string
  min_adv_inr: string
  exclude_surveillance: boolean
  exclude_corporate_actions: boolean
  direction: 'ALL' | 'LONG' | 'SHORT'
  sectors: string[]
}

export const DEFAULT_FILTERS: UniverseFilterState = {
  asset_class: 'ALL',
  min_price: '',
  max_price: '',
  min_adv_inr: '',
  exclude_surveillance: true,
  exclude_corporate_actions: true,
  direction: 'ALL',
  sectors: [],
}

export function filtersToPayload(f: UniverseFilterState): Record<string, unknown> {
  return {
    asset_class: f.asset_class,
    min_price: f.min_price || null,
    max_price: f.max_price || null,
    min_adv_inr: f.min_adv_inr || null,
    exclude_surveillance: f.exclude_surveillance,
    exclude_corporate_actions: f.exclude_corporate_actions,
    direction: f.direction,
    sectors: f.sectors || [],
  }
}

export type FilterPreset = {
  id: string
  name: string
  filters: UniverseFilterState
  builtin?: boolean
}

export const BUILTIN_PRESETS: FilterPreset[] = [
  {
    id: 'liquid',
    name: 'Liquid large-cap',
    builtin: true,
    filters: {
      ...DEFAULT_FILTERS,
      asset_class: 'STOCK',
      min_adv_inr: '200000000',
      min_price: '50',
    },
  },
  {
    id: 'etf',
    name: 'ETF only',
    builtin: true,
    filters: { ...DEFAULT_FILTERS, asset_class: 'ETF' },
  },
  {
    id: 'rvol',
    name: 'High RVOL morning',
    builtin: true,
    filters: { ...DEFAULT_FILTERS, asset_class: 'STOCK', min_adv_inr: '50000000' },
  },
]

export const CUSTOM_PRESETS_KEY = 'tp_filter_presets_v1'
const SECTOR_OPTIONS = ['BANKING', 'IT', 'ENERGY', 'AUTO', 'PHARMA', 'FMCG', 'METALS', 'UNKNOWN']

type UniverseOption = { value: string; label: string }

type PreviewResponse = {
  universe_total: number
  after_filters: number
  quotes_applied?: boolean
  quotes_coverage?: number
  drop_reasons?: Record<string, number>
}

type Props = {
  value: UniverseFilterState
  onChange: (next: UniverseFilterState) => void
  universe?: string
  onUniverseChange?: (next: string) => void
  universeOptions?: UniverseOption[]
  matchCount?: number | null
  universeTotal?: number | null
  universeLabel?: string
  compact?: boolean
  strategyLabel?: string
  /** Modal mode (UC-B2) */
  open?: boolean
  onClose?: () => void
  baseUrl?: string
  onManagePresets?: () => void
}

export function readCustomPresets(): FilterPreset[] {
  try {
    const raw = localStorage.getItem(CUSTOM_PRESETS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as FilterPreset[]
    if (!Array.isArray(parsed)) return []
    return parsed.filter((p) => p && typeof p.id === 'string' && typeof p.name === 'string' && p.filters)
  } catch {
    return []
  }
}

export function writeCustomPresets(presets: FilterPreset[]) {
  localStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(presets))
}

export function normalizeFilters(raw: Partial<UniverseFilterState> | UniverseFilterState): UniverseFilterState {
  return {
    ...DEFAULT_FILTERS,
    ...raw,
    sectors: Array.isArray(raw.sectors) ? raw.sectors : [],
  }
}

export function listAllPresets(): FilterPreset[] {
  return [...BUILTIN_PRESETS, ...readCustomPresets()]
}

export function saveNamedPreset(name: string, filters: UniverseFilterState, replaceId?: string | null): FilterPreset {
  const trimmed = name.trim() || `My filters ${Date.now()}`
  const custom = readCustomPresets()
  const canReplace = Boolean(replaceId && custom.some((p) => p.id === replaceId))
  const next: FilterPreset = {
    id: canReplace && replaceId ? replaceId : `custom-${Date.now()}`,
    name: trimmed,
    filters: normalizeFilters(filters),
  }
  const without = custom.filter((p) => p.id !== next.id && p.name.toLowerCase() !== trimmed.toLowerCase())
  writeCustomPresets([...without, next])
  return next
}

export function deleteCustomPreset(id: string) {
  writeCustomPresets(readCustomPresets().filter((p) => p.id !== id))
}

function assetChecks(assetClass: UniverseFilterState['asset_class']) {
  return {
    stocks: assetClass === 'ALL' || assetClass === 'STOCK',
    etfs: assetClass === 'ALL' || assetClass === 'ETF',
  }
}

function assetClassFromChecks(stocks: boolean, etfs: boolean): UniverseFilterState['asset_class'] {
  if (stocks && etfs) return 'ALL'
  if (stocks) return 'STOCK'
  if (etfs) return 'ETF'
  return 'ALL'
}

export function FilterBuilder({
  value,
  onChange,
  universe,
  onUniverseChange,
  universeOptions,
  matchCount,
  universeTotal,
  universeLabel,
  compact,
  strategyLabel = 'BreakoutRetest',
  open,
  onClose,
  baseUrl,
  onManagePresets,
}: Props) {
  function set<K extends keyof UniverseFilterState>(key: K, v: UniverseFilterState[K]) {
    onChange({ ...value, [key]: v })
  }

  if (compact) {
    return (
      <div className="filter-builder compact">
        <div className="filter-presets">
          {BUILTIN_PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className="secondary-button"
              onClick={() => onChange(normalizeFilters(p.filters))}
            >
              {p.name}
            </button>
          ))}
        </div>
        <div className="filter-grid">
          <label className="field">
            <span>Asset class</span>
            <select
              value={value.asset_class}
              onChange={(e) => set('asset_class', e.target.value as UniverseFilterState['asset_class'])}
            >
              <option value="ALL">Stocks + ETFs</option>
              <option value="STOCK">Stocks</option>
              <option value="ETF">ETFs</option>
            </select>
          </label>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={value.exclude_surveillance}
              onChange={(e) => set('exclude_surveillance', e.target.checked)}
            />
            <span>Exclude ASM</span>
          </label>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={value.exclude_corporate_actions}
              onChange={(e) => set('exclude_corporate_actions', e.target.checked)}
            />
            <span>Exclude CA</span>
          </label>
        </div>
      </div>
    )
  }

  const isModal = open != null

  if (isModal && !open) return null

  const body = (
    <FilterBuilderBody
      value={value}
      onChange={onChange}
      universe={universe || universeLabel || 'NSE_ALL'}
      onUniverseChange={onUniverseChange}
      universeOptions={universeOptions}
      strategyLabel={strategyLabel}
      baseUrl={baseUrl}
      externalMatchCount={matchCount}
      externalUniverseTotal={universeTotal}
      onClose={onClose}
      showClose={isModal}
      onManagePresets={onManagePresets}
    />
  )

  if (!isModal) {
    return <div className="filter-builder wireframe-filters">{body}</div>
  }

  return createPortal(
    <div className="filter-overlay" role="presentation">
      <div
        className="filter-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="filter-builder-title"
      >
        {body}
      </div>
    </div>,
    document.body,
  )
}

type BodyProps = {
  value: UniverseFilterState
  onChange: (next: UniverseFilterState) => void
  universe: string
  onUniverseChange?: (next: string) => void
  universeOptions?: UniverseOption[]
  strategyLabel: string
  baseUrl?: string
  externalMatchCount?: number | null
  externalUniverseTotal?: number | null
  onClose?: () => void
  showClose?: boolean
  onManagePresets?: () => void
}

function FilterBuilderBody({
  value,
  onChange,
  universe,
  onUniverseChange,
  universeOptions,
  strategyLabel,
  baseUrl,
  externalMatchCount,
  externalUniverseTotal,
  onClose,
  showClose,
  onManagePresets,
}: BodyProps) {
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [customPresets, setCustomPresets] = useState<FilterPreset[]>(() => readCustomPresets())
  const [presetName, setPresetName] = useState('')
  const [savedFlash, setSavedFlash] = useState(false)
  const [activePresetId, setActivePresetId] = useState<string | null>(null)

  const checks = assetChecks(value.asset_class)
  const allPresets = useMemo(() => [...BUILTIN_PRESETS, ...customPresets], [customPresets])

  useEffect(() => {
    if (!showClose) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [showClose])

  useEffect(() => {
    if (!baseUrl) return
    let cancelled = false
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setLoading(true)
      setError('')
      void (async () => {
        try {
          const res = await fetch(`${baseUrl}/api/v1/universe/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              universe,
              filters: filtersToPayload(value),
            }),
            signal: controller.signal,
          })
          if (!res.ok) throw new Error('Could not preview filters')
          const data = (await res.json()) as PreviewResponse
          if (!cancelled) setPreview(data)
        } catch (err) {
          if (cancelled || (err instanceof DOMException && err.name === 'AbortError')) return
          setError(err instanceof Error ? err.message : 'Could not preview filters')
          setPreview(null)
        } finally {
          if (!cancelled) setLoading(false)
        }
      })()
    }, 280)
    return () => {
      cancelled = true
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [baseUrl, universe, value])

  function set<K extends keyof UniverseFilterState>(key: K, v: UniverseFilterState[K]) {
    setActivePresetId(null)
    onChange({ ...value, [key]: v })
  }

  function setAssetChecks(nextStocks: boolean, nextEtfs: boolean) {
    set('asset_class', assetClassFromChecks(nextStocks, nextEtfs))
  }

  function applyPreset(preset: FilterPreset) {
    onChange(normalizeFilters(preset.filters))
    setActivePresetId(preset.id)
  }

  function saveCurrentPreset() {
    const saved = saveNamedPreset(presetName.trim() || `My filters ${customPresets.length + 1}`, value)
    setCustomPresets(readCustomPresets())
    setActivePresetId(saved.id)
    setPresetName('')
    setSavedFlash(true)
    window.setTimeout(() => setSavedFlash(false), 1600)
  }

  const matchCount =
    preview?.after_filters ?? externalMatchCount ?? null
  const total = preview?.universe_total ?? externalUniverseTotal ?? null
  const options =
    universeOptions && universeOptions.length > 0
      ? universeOptions
      : [{ value: universe, label: universe.replace(/_/g, ' ') }]

  return (
    <>
      <header className="filter-modal-head">
        <h1 id="filter-builder-title">Filters</h1>
        {showClose && onClose ? (
          <button type="button" className="ghost-btn filter-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        ) : null}
      </header>

      <div className="filter-builder-columns">
        <section className="filter-col filters-col">
          <h3>Filters</h3>

          <label className="field" htmlFor="filter-universe">
            <span>Universe</span>
            <select
              id="filter-universe"
              value={universe}
              disabled={!onUniverseChange}
              onChange={(e) => onUniverseChange?.(e.target.value)}
            >
              {options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="filter-fieldset">
            <legend>Asset class</legend>
            <label className="filter-check">
              <input
                type="checkbox"
                checked={checks.stocks}
                onChange={(e) => setAssetChecks(e.target.checked, checks.etfs || !e.target.checked)}
              />
              <span>Stocks</span>
            </label>
            <label className="filter-check">
              <input
                type="checkbox"
                checked={checks.etfs}
                onChange={(e) => setAssetChecks(checks.stocks || !e.target.checked, e.target.checked)}
              />
              <span>ETFs</span>
            </label>
          </fieldset>

          <div className="field-row two-col">
            <label className="field">
              <span>Price min</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={value.min_price}
                onChange={(e) => set('min_price', e.target.value)}
                placeholder="—"
              />
            </label>
            <label className="field">
              <span>Price max</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={value.max_price}
                onChange={(e) => set('max_price', e.target.value)}
                placeholder="—"
              />
            </label>
          </div>

          <label className="field">
            <span>ADV min (₹)</span>
            <input
              type="number"
              min="0"
              step="1000"
              value={value.min_adv_inr}
              onChange={(e) => set('min_adv_inr', e.target.value)}
              placeholder="—"
            />
          </label>

          <label className="field">
            <span>Sector (multi-select)</span>
            <select
              multiple
              size={4}
              value={value.sectors}
              onChange={(e) => {
                const selected = Array.from(e.target.selectedOptions).map((o) => o.value)
                set('sectors', selected)
              }}
            >
              {SECTOR_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <span className="field-hint">Hold Ctrl/Cmd to select multiple</span>
          </label>

          <div className="filter-toggles">
            <span className="field-label">Exclude ASM / CA</span>
            <label className="toggle-row">
              <span>Exclude ASM</span>
              <input
                type="checkbox"
                role="switch"
                checked={value.exclude_surveillance}
                onChange={(e) => set('exclude_surveillance', e.target.checked)}
              />
            </label>
            <label className="toggle-row">
              <span>Exclude CA</span>
              <input
                type="checkbox"
                role="switch"
                checked={value.exclude_corporate_actions}
                onChange={(e) => set('exclude_corporate_actions', e.target.checked)}
              />
            </label>
          </div>

          <label className="field">
            <span>TA strategy</span>
            <input value={strategyLabel} readOnly />
          </label>

          <label className="field">
            <span>Direction</span>
            <select
              value={value.direction}
              onChange={(e) => set('direction', e.target.value as UniverseFilterState['direction'])}
            >
              <option value="ALL">All</option>
              <option value="LONG">Long</option>
              <option value="SHORT">Short</option>
            </select>
          </label>
        </section>

        <section className="filter-col results-col">
          <h3>Filtered Results</h3>
          <p className="filter-result-count" aria-live="polite">
            {loading ? '…' : matchCount != null ? matchCount.toLocaleString('en-IN') : '—'}
          </p>
          <p className="filter-result-label">stocks and ETFs</p>
          {total != null && (
            <p className="field-hint">of {total.toLocaleString('en-IN')} in universe</p>
          )}
          {preview?.quotes_applied && (
            <p className="field-hint">
              Price/ADV applied using {preview.quotes_coverage?.toLocaleString('en-IN') ?? '—'} names with
              1d candles.
            </p>
          )}
          {error && <p className="status error">{error}</p>}
          <hr className="filter-rule" />
          <label className="field">
            <span>Preset name</span>
            <input
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              placeholder="My swing defaults"
            />
          </label>
          <button type="button" className="primary-button universe-save-btn" onClick={saveCurrentPreset}>
            <span className="universe-save-icon" aria-hidden="true" />
            {savedFlash ? 'Preset saved' : 'Save preset'}
          </button>
          <p className="field-hint">Save current filter settings as a preset</p>
        </section>

        <section className="filter-col presets-col">
          <h3>Saved Presets</h3>
          <ul className="preset-list">
            {allPresets.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={`preset-chip ${activePresetId === p.id ? 'active' : ''}`}
                  onClick={() => applyPreset(p)}
                >
                  <span aria-hidden="true">★</span> {p.name}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="universe-manage-btn manage-presets"
            onClick={() => onManagePresets?.()}
          >
            <span className="universe-gear-icon" aria-hidden="true" />
            <span>Manage presets</span>
            <span className="universe-chevron" aria-hidden="true" />
          </button>
        </section>
      </div>

      <aside className="beginner-hint">
        <span className="beginner-hint-icon" aria-hidden="true" />
        <div>
          <strong>Beginner hint</strong>
          <p>
            Why filters matter: Narrow your universe to find higher-probability setups, reduce noise and save
            time.
          </p>
        </div>
      </aside>
    </>
  )
}
