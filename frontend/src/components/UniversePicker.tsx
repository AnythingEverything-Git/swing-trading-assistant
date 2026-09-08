import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

export type ScanUniverse = 'NSE_ALL' | 'NSE_CASH' | 'NSE_ETF' | 'NIFTY_50' | 'NIFTY_100' | 'NIFTY_200' | 'NIFTY_500'

type PreviewResponse = {
  universe: string
  universe_total: number
  after_filters: number
  equity_count?: number
  etf_count?: number
}

type Props = {
  open: boolean
  onClose: () => void
  baseUrl: string
  value: ScanUniverse
  onChange: (next: ScanUniverse) => void
  onManagePresets?: () => void
}

const SCOPE_OPTIONS: { value: ScanUniverse; label: string }[] = [
  { value: 'NSE_ALL', label: 'NSE all' },
  { value: 'NSE_CASH', label: 'Stocks only' },
  { value: 'NSE_ETF', label: 'ETFs only' },
]

const NIFTY_SHORTCUTS: { value: ScanUniverse; label: string }[] = [
  { value: 'NIFTY_50', label: 'Nifty 50' },
  { value: 'NIFTY_100', label: 'Nifty 100' },
  { value: 'NIFTY_500', label: 'Nifty 500' },
]

const UNIVERSE_PRESET_KEY = 'tp_universe_preset'

const ALL_UNIVERSES: ScanUniverse[] = [
  'NSE_ALL',
  'NSE_CASH',
  'NSE_ETF',
  'NIFTY_50',
  'NIFTY_100',
  'NIFTY_200',
  'NIFTY_500',
]

async function fetchPreview(baseUrl: string, universe: string, signal?: AbortSignal): Promise<PreviewResponse> {
  const res = await fetch(`${baseUrl}/api/v1/universe/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      universe,
      filters: {
        asset_class: 'ALL',
        exclude_surveillance: false,
        exclude_corporate_actions: false,
      },
    }),
    signal,
  })
  if (!res.ok) throw new Error('Could not load universe size')
  return (await res.json()) as PreviewResponse
}

function fallbackAssetCounts(universe: ScanUniverse, total: number, cashTotal: number, etfTotal: number) {
  if (universe === 'NSE_ETF') return { equity: 0, etf: total }
  if (universe === 'NSE_CASH' || universe.startsWith('NIFTY')) return { equity: total, etf: 0 }
  return { equity: cashTotal, etf: etfTotal }
}

export function UniversePicker({
  open,
  onClose,
  baseUrl,
  value,
  onChange,
  onManagePresets,
}: Props) {
  const [draft, setDraft] = useState<ScanUniverse>(value)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [equityCount, setEquityCount] = useState<number | null>(null)
  const [etfCount, setEtfCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [savedFlash, setSavedFlash] = useState(false)
  const [presetsOpen, setPresetsOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    setDraft(value)
    setSavedFlash(false)
    setPresetsOpen(false)
  }, [open, value])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void (async () => {
      try {
        const data = await fetchPreview(baseUrl, draft, controller.signal)
        if (cancelled) return
        setPreview(data)

        if (typeof data.equity_count === 'number' && typeof data.etf_count === 'number') {
          setEquityCount(data.equity_count)
          setEtfCount(data.etf_count)
        } else {
          const [cash, etf] = await Promise.all([
            fetchPreview(baseUrl, 'NSE_CASH', controller.signal),
            fetchPreview(baseUrl, 'NSE_ETF', controller.signal),
          ])
          if (cancelled) return
          const counts = fallbackAssetCounts(draft, data.universe_total, cash.universe_total, etf.universe_total)
          setEquityCount(counts.equity)
          setEtfCount(counts.etf)
        }
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === 'AbortError')) return
        setError(err instanceof Error ? err.message : 'Could not load universe size')
        setPreview(null)
        setEquityCount(null)
        setEtfCount(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [baseUrl, draft, open])

  function selectUniverse(next: ScanUniverse) {
    setDraft(next)
    onChange(next)
  }

  function savePreset() {
    try {
      localStorage.setItem(
        UNIVERSE_PRESET_KEY,
        JSON.stringify({ universe: draft, savedAt: new Date().toISOString() }),
      )
      setSavedFlash(true)
      window.setTimeout(() => setSavedFlash(false), 1600)
    } catch {
      /* ignore */
    }
  }

  function loadSavedPreset() {
    try {
      const raw = localStorage.getItem(UNIVERSE_PRESET_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as { universe?: string }
      const next = parsed.universe as ScanUniverse | undefined
      if (next && ALL_UNIVERSES.includes(next)) selectUniverse(next)
    } catch {
      /* ignore */
    }
    setPresetsOpen(false)
  }

  if (!open) return null

  const matchCount = preview?.universe_total ?? null
  const titleLabel = draft.replace(/_/g, ' ')

  return createPortal(
    <div className="universe-overlay" role="presentation">
      <div
        className="universe-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="universe-picker-title"
      >
        <header className="universe-modal-head">
          <h1 id="universe-picker-title">Universe: {titleLabel}</h1>
          <button type="button" className="ghost-btn universe-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="universe-picker-grid">
          <article className="universe-picker-card">
            <h3>Universe</h3>
            <div className="universe-radio-list" role="radiogroup" aria-label="Master universe">
              {SCOPE_OPTIONS.map((opt) => (
                <label key={opt.value} className="universe-radio">
                  <input
                    type="radio"
                    name="universe-scope"
                    checked={draft === opt.value}
                    onChange={() => selectUniverse(opt.value)}
                  />
                  <span>{opt.label}</span>
                </label>
              ))}
            </div>
            <hr className="universe-picker-rule" />
            <p className="universe-picker-sub">Nifty shortcuts</p>
            <div className="universe-nifty-row">
              {NIFTY_SHORTCUTS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`universe-nifty-btn ${draft === opt.value ? 'active' : ''}`}
                  onClick={() => selectUniverse(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </article>

          <article className="universe-picker-card universe-picker-card-match">
            <p className="universe-match-label">Matching symbols</p>
            <p className="universe-match-count" aria-live="polite">
              {loading ? '…' : matchCount != null ? matchCount.toLocaleString('en-IN') : '—'}
            </p>
            <p className="universe-match-hint">Master list is full NSE — filters shrink results only.</p>
            {error && <p className="status error">{error}</p>}
            <hr className="universe-picker-rule" />
            <button type="button" className="primary-button universe-save-btn" onClick={savePreset}>
              <span className="universe-save-icon" aria-hidden="true" />
              {savedFlash ? 'Preset saved' : 'Save preset'}
            </button>
          </article>

          <article className="universe-picker-card">
            <h3>Asset class</h3>
            <div className="universe-asset-row">
              <div className="universe-asset-chip">
                Equity {equityCount != null ? equityCount.toLocaleString('en-IN') : loading ? '…' : '—'}
              </div>
              <div className="universe-asset-chip">
                ETF {etfCount != null ? etfCount.toLocaleString('en-IN') : loading ? '…' : '—'}
              </div>
            </div>
            <hr className="universe-picker-rule" />
            <button
              type="button"
              className="universe-manage-btn"
              onClick={() => {
                if (onManagePresets) onManagePresets()
                else setPresetsOpen((o) => !o)
              }}
            >
              <span className="universe-gear-icon" aria-hidden="true" />
              <span>Manage presets</span>
              <span className="universe-chevron" aria-hidden="true" />
            </button>
            {presetsOpen && (
              <div className="universe-presets-panel">
                <button type="button" className="secondary-button" onClick={loadSavedPreset}>
                  Load saved universe
                </button>
                <p className="field-hint">Full filter presets arrive in UC-B3.</p>
              </div>
            )}
          </article>
        </div>

        <p className="universe-picker-note">Filtering only inside the app.</p>
      </div>
    </div>,
    document.body,
  )
}
