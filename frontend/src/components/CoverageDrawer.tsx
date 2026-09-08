import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { filtersToPayload, type UniverseFilterState } from './FilterBuilder'

export type CoverageSummary = {
  eligible: number
  filtered: number
  no_candles: number
  surveillance: number
  ca_day: number
  universe_total: number
  after_filters: number
}

export type CoverageRow = {
  symbol: string
  bucket: string
  reason: string
  code?: string
}

type CoverageResponse = {
  universe: string
  summary: CoverageSummary
  rows: CoverageRow[]
  rows_total: number
  truncated: boolean
  note?: string
}

type KpiKey = 'all' | 'eligible' | 'filtered' | 'no_candles' | 'surveillance' | 'ca_day'

type Props = {
  open: boolean
  onClose: () => void
  baseUrl: string
  universe: string
  filters: UniverseFilterState
  /** Optional scan-window issues merged into the table */
  scanIssues?: { symbol: string; status: string; detail?: string }[] | null
  dataAsOf?: string | null
  formatDateTime: (value: string | null | undefined) => string
}

const KPI_META: { key: KpiKey; label: string; codes?: string[] }[] = [
  { key: 'eligible', label: 'Eligible' },
  { key: 'filtered', label: 'Filtered', codes: ['ASSET_CLASS', 'SECTOR', 'MIN_PRICE', 'MAX_PRICE', 'MIN_ADV'] },
  { key: 'no_candles', label: 'No candles', codes: ['NO_CANDLES', 'UNAVAILABLE'] },
  { key: 'surveillance', label: 'Surveillance', codes: ['SURVEILLANCE'] },
  { key: 'ca_day', label: 'CA day', codes: ['CORPORATE_ACTION'] },
]

function downloadCsv(filename: string, rows: CoverageRow[]) {
  const header = 'symbol,bucket,reason,code'
  const body = rows
    .map((r) =>
      [r.symbol, r.bucket, r.reason, r.code || '']
        .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
        .join(','),
    )
    .join('\n')
  const blob = new Blob([`${header}\n${body}\n`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function CoverageDrawer({
  open,
  onClose,
  baseUrl,
  universe,
  filters,
  scanIssues,
  dataAsOf,
  formatDateTime,
}: Props) {
  const [data, setData] = useState<CoverageResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [kpi, setKpi] = useState<KpiKey>('all')
  const [refreshKey, setRefreshKey] = useState(0)

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
        const res = await fetch(`${baseUrl}/api/v1/universe/coverage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            universe,
            filters: filtersToPayload(filters),
            limit: 800,
          }),
          signal: controller.signal,
        })
        if (!res.ok) throw new Error('Could not load coverage')
        const payload = (await res.json()) as CoverageResponse
        if (!cancelled) setData(payload)
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === 'AbortError')) return
        setError(err instanceof Error ? err.message : 'Could not load coverage')
        setData(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [open, baseUrl, universe, filters, refreshKey])

  const mergedRows = useMemo(() => {
    const base = data?.rows ?? []
    const bySymbol = new Map(base.map((r) => [r.symbol, r]))
    for (const issue of scanIssues || []) {
      if (issue.status !== 'UNAVAILABLE' && issue.status !== 'ERROR') continue
      if (bySymbol.has(issue.symbol)) continue
      bySymbol.set(issue.symbol, {
        symbol: issue.symbol,
        bucket: issue.status === 'UNAVAILABLE' ? 'No 1d candles' : 'Error',
        reason:
          issue.status === 'UNAVAILABLE'
            ? 'Missing daily price data in scan window'
            : issue.detail || 'Evaluator error',
        code: issue.status === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'ERROR',
      })
    }
    return Array.from(bySymbol.values())
  }, [data, scanIssues])

  const summary = data?.summary
  const filteredRows = useMemo(() => {
    if (kpi === 'all') return mergedRows
    if (kpi === 'eligible') return []
    const meta = KPI_META.find((k) => k.key === kpi)
    const codes = new Set(meta?.codes || [])
    return mergedRows.filter((r) => codes.has(r.code || ''))
  }, [mergedRows, kpi])

  if (!open) return null

  return createPortal(
    <div className="coverage-overlay" role="presentation">
      <div
        className="coverage-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="coverage-drawer-title"
      >
        <header className="filter-modal-head">
          <h1 id="coverage-drawer-title">Coverage drawer</h1>
          <button type="button" className="ghost-btn filter-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="coverage-kpi-row" role="tablist" aria-label="Coverage buckets">
          {KPI_META.map((item) => {
            const value =
              item.key === 'eligible'
                ? summary?.eligible
                : item.key === 'filtered'
                  ? summary?.filtered
                  : item.key === 'no_candles'
                    ? summary?.no_candles
                    : item.key === 'surveillance'
                      ? summary?.surveillance
                      : summary?.ca_day
            const active = kpi === item.key
            return (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={active}
                className={`coverage-kpi ${active ? 'active' : ''}`}
                onClick={() => setKpi(active ? 'all' : item.key)}
              >
                <span>{item.label}</span>
                <strong>{loading ? '…' : value != null ? value.toLocaleString('en-IN') : '—'}</strong>
              </button>
            )
          })}
        </div>

        {error ? <p className="status error">{error}</p> : null}

        <div className="table-wrap coverage-table-wrap">
          <table className="coverage-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Bucket</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {kpi === 'eligible' ? (
                <tr>
                  <td colSpan={3} className="coverage-empty">
                    {loading
                      ? 'Loading…'
                      : `${(summary?.eligible ?? 0).toLocaleString('en-IN')} symbols passed filters and have 1d candles — ready for scan / morning board.`}
                  </td>
                </tr>
              ) : filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={3} className="coverage-empty">
                    {loading ? 'Loading…' : 'No skips in this bucket.'}
                  </td>
                </tr>
              ) : (
                filteredRows.map((row) => (
                  <tr key={`${row.symbol}-${row.code || row.bucket}`}>
                    <td>{row.symbol}</td>
                    <td>{row.bucket}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {data?.truncated ? (
          <p className="field-hint">
            Showing {data.rows.length.toLocaleString('en-IN')} of {data.rows_total.toLocaleString('en-IN')} skip
            rows — export CSV for the loaded sample.
          </p>
        ) : null}

        <div className="coverage-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={filteredRows.length === 0 && kpi !== 'eligible'}
            onClick={() =>
              downloadCsv(
                `tradepilot-coverage-${universe.toLowerCase()}.csv`,
                kpi === 'eligible' ? [] : filteredRows.length ? filteredRows : mergedRows,
              )
            }
          >
            Export skip list CSV
          </button>
          <p className="field-hint">{data?.note || 'Note: Unified coverage for Swing and Intraday.'}</p>
        </div>

        <footer className="coverage-footer">
          <p className="coverage-disclaimer">Not financial advice. Trading involves risk.</p>
          <div className="coverage-footer-right">
            <span>Data as of {dataAsOf ? formatDateTime(dataAsOf) : '—'}</span>
            <button
              type="button"
              className="secondary-button coverage-refresh"
              onClick={() => setRefreshKey((k) => k + 1)}
              disabled={loading}
            >
              <span className="coverage-refresh-icon" aria-hidden="true" />
              Refresh
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  )
}
