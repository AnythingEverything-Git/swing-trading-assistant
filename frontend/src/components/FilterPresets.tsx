import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BUILTIN_PRESETS,
  deleteCustomPreset,
  filtersToPayload,
  listAllPresets,
  normalizeFilters,
  readCustomPresets,
  saveNamedPreset,
  type FilterPreset,
  type UniverseFilterState,
} from './FilterBuilder'

type Props = {
  open: boolean
  onClose: () => void
  baseUrl: string
  universe: string
  value: UniverseFilterState
  onChange: (next: UniverseFilterState) => void
  /** Apply preset and open filter builder for editing */
  onEdit: (filters: UniverseFilterState) => void
}

type PreviewResponse = {
  universe_total: number
  after_filters: number
}

export function FilterPresets({
  open,
  onClose,
  baseUrl,
  universe,
  value,
  onChange,
  onEdit,
}: Props) {
  const [presets, setPresets] = useState<FilterPreset[]>(() => listAllPresets())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [previewFilters, setPreviewFilters] = useState<UniverseFilterState>(value)
  const [presetName, setPresetName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState('')

  useEffect(() => {
    if (!open) return
    setPresets(listAllPresets())
    setPreviewFilters(value)
    setSelectedId(null)
    setEditingId(null)
    setPresetName('')
    setFlash('')
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
              filters: filtersToPayload(previewFilters),
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
    }, 220)
    return () => {
      cancelled = true
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [baseUrl, universe, previewFilters, open])

  const selected = useMemo(
    () => presets.find((p) => p.id === selectedId) ?? null,
    [presets, selectedId],
  )

  function refreshList() {
    setPresets(listAllPresets())
  }

  function selectForPreview(preset: FilterPreset) {
    setSelectedId(preset.id)
    setPreviewFilters(normalizeFilters(preset.filters))
  }

  function handleApply(preset: FilterPreset) {
    const next = normalizeFilters(preset.filters)
    onChange(next)
    setPreviewFilters(next)
    setSelectedId(preset.id)
    setFlash(`Applied “${preset.name}”`)
    window.setTimeout(() => setFlash(''), 1600)
  }

  function handleEdit(preset: FilterPreset) {
    const next = normalizeFilters(preset.filters)
    onChange(next)
    if (!preset.builtin) {
      setEditingId(preset.id)
      setPresetName(preset.name)
    }
    onEdit(next)
  }

  function handleSave() {
    const name = presetName.trim() || 'My swing defaults'
    const saved = saveNamedPreset(name, value, editingId)
    refreshList()
    setSelectedId(saved.id)
    setPreviewFilters(normalizeFilters(saved.filters))
    setEditingId(null)
    setPresetName('')
    setFlash(`Saved “${saved.name}”`)
    window.setTimeout(() => setFlash(''), 1600)
  }

  function handleDelete(id: string) {
    deleteCustomPreset(id)
    refreshList()
    if (selectedId === id) {
      setSelectedId(null)
      setPreviewFilters(value)
    }
    if (editingId === id) {
      setEditingId(null)
      setPresetName('')
    }
  }

  if (!open) return null

  const matchCount = preview?.after_filters ?? null

  return createPortal(
    <div className="presets-overlay" role="presentation">
      <div
        className="presets-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="filter-presets-title"
      >
        <header className="filter-modal-head">
          <h1 id="filter-presets-title">Filter presets</h1>
          <button type="button" className="ghost-btn filter-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="presets-grid">
          <section className="filter-col presets-list-col">
            <ul className="presets-row-list">
              {presets.map((p) => (
                <li key={p.id} className={selectedId === p.id ? 'is-selected' : ''}>
                  <button type="button" className="presets-row-name" onClick={() => selectForPreview(p)}>
                    {p.name}
                    {p.builtin ? <span className="presets-builtin-tag">built-in</span> : null}
                  </button>
                  <div className="presets-row-actions">
                    <button type="button" className="secondary-button presets-mini-btn" onClick={() => handleApply(p)}>
                      Apply
                    </button>
                    <button type="button" className="secondary-button presets-mini-btn" onClick={() => handleEdit(p)}>
                      Edit
                    </button>
                    {!p.builtin ? (
                      <button type="button" className="link-button" onClick={() => handleDelete(p.id)}>
                        Delete
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
            {presets.length === BUILTIN_PRESETS.length && readCustomPresets().length === 0 ? (
              <p className="field-hint">Save your own preset on the right to add “My swing defaults”.</p>
            ) : null}
          </section>

          <section className="filter-col results-col">
            <h3>Filtered Results</h3>
            <p className="filter-result-count" aria-live="polite">
              {loading ? '…' : matchCount != null ? matchCount.toLocaleString('en-IN') : '—'}
            </p>
            <p className="filter-result-label">stocks and ETFs</p>
            {selected ? (
              <p className="field-hint">Preview: {selected.name}</p>
            ) : (
              <p className="field-hint">Preview uses your current filters</p>
            )}
            {error ? <p className="status error">{error}</p> : null}
            {flash ? <p className="presets-flash">{flash}</p> : null}
          </section>

          <section className="filter-col presets-save-col">
            <h3>Save current filters</h3>
            <hr className="filter-rule" />
            <label className="field">
              <span>Name</span>
              <input
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                placeholder="Name"
                autoFocus
              />
            </label>
            <button type="button" className="primary-button" onClick={handleSave}>
              {editingId ? 'Update preset' : 'Save preset'}
            </button>
            {editingId ? (
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setEditingId(null)
                  setPresetName('')
                }}
              >
                Cancel update
              </button>
            ) : (
              <p className="field-hint">Saves the filters currently active on Swing desk.</p>
            )}
          </section>
        </div>

        <aside className="beginner-hint">
          <span className="beginner-hint-icon" aria-hidden="true" />
          <div>
            <strong>Disclaimer</strong>
            <p>
              Saved presets are user-defined configurations. Ensure your filter settings are accurate before
              saving.
            </p>
          </div>
        </aside>
      </div>
    </div>,
    document.body,
  )
}
