import { useMemo, useState } from 'react'
import type { ScanRunSummary } from '../scan/types'

export function scanEligiblePct(run: ScanRunSummary): number | null {
  const eligible = Number(run.eligible_count ?? run.result_count ?? 0)
  const scanned = Number(run.symbols_scanned ?? 0)
  if (!scanned || !Number.isFinite(eligible)) return null
  return Math.max(0, Math.min(100, (100 * eligible) / scanned))
}

export function scanCoveragePct(run: ScanRunSummary): number | null {
  const scanned = Number(run.symbols_scanned ?? 0)
  const after = Number(run.filter_coverage?.after_filters ?? scanned)
  if (!after || !Number.isFinite(scanned)) return null
  return Math.max(0, Math.min(100, (100 * scanned) / after))
}

function formatDay(value: string | null | undefined): string {
  if (!value) return '—'
  const day = value.slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : value
}

function formatPct(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${Math.round(value)}%`
}

type Props = {
  runs: ScanRunSummary[]
  selectedId: number | null
  onSelect: (id: number) => void
  onOpen: (id: number) => void | Promise<void>
  onExportCsv: (id: number) => void | Promise<void>
  busyId: number | null
  error: string
  coveragePct: number | null
  dataAsOf: string | null
  onRefresh: () => void
  refreshing: boolean
  formatDateTime: (value: string | null | undefined) => string
}

export function ScanHistoryDesk({
  runs,
  selectedId,
  onSelect,
  onOpen,
  onExportCsv,
  busyId,
  error,
  coveragePct,
  dataAsOf,
  onRefresh,
  refreshing,
  formatDateTime,
}: Props) {
  const [exportingId, setExportingId] = useState<number | null>(null)

  const selected = useMemo(
    () => runs.find((run) => run.id === selectedId) ?? runs[0] ?? null,
    [runs, selectedId],
  )

  const selectedEligible = selected ? scanEligiblePct(selected) : null
  const selectedCoverage = selected ? scanCoveragePct(selected) : null
  const footerCoverage = coveragePct ?? selectedCoverage
  const topIdeasCount = selected?.top_count ?? null

  async function handleExport(id: number) {
    setExportingId(id)
    try {
      await onExportCsv(id)
    } finally {
      setExportingId(null)
    }
  }

  return (
    <section className="scan-history" aria-label="Scan history runs">
      {error ? <div className="status error">{error}</div> : null}

      <div className="scan-history-layout">
        <div className="scan-history-main">
          {runs.length === 0 ? (
            <p className="field-hint scan-history-empty">No completed scans yet. Run Find setups to build history.</p>
          ) : (
            <div className="scan-history-table-wrap">
              <table className="scan-history-table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Universe</th>
                    <th scope="col" className="num">
                      Eligible
                    </th>
                    <th scope="col" className="num">
                      Coverage
                    </th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const active = (selected?.id ?? null) === run.id
                    const busy = busyId === run.id || exportingId === run.id
                    const status = (run.status ?? 'completed').toLowerCase()
                    const canOpen = status === 'completed'
                    return (
                      <tr
                        key={run.id}
                        className={active ? 'is-selected' : undefined}
                        onClick={() => onSelect(run.id)}
                      >
                        <td>
                          <span className="scan-history-date">{formatDay(run.started_at)}</span>
                          {status !== 'completed' ? (
                            <span className={`scan-history-status is-${status}`}>{status}</span>
                          ) : null}
                        </td>
                        <td>{run.universe_name || '—'}</td>
                        <td className="num">{formatPct(scanEligiblePct(run))}</td>
                        <td className="num">{formatPct(scanCoveragePct(run))}</td>
                        <td className="scan-history-actions" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            className="secondary-button find-tool-btn"
                            disabled={!canOpen || busy}
                            onClick={() => void onOpen(run.id)}
                          >
                            {busyId === run.id ? 'Opening…' : 'Open'}
                          </button>
                          <button
                            type="button"
                            className="secondary-button find-tool-btn"
                            disabled={!canOpen || busy}
                            onClick={() => void handleExport(run.id)}
                          >
                            {exportingId === run.id ? 'Exporting…' : 'Export CSV'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <aside className="scan-history-rail" aria-label="Selected scan summary">
          <div className="scan-history-summary">
            <h3 className="inspect-tile-label">Selected scan summary</h3>
            {selected ? (
              <>
                <dl className="scan-history-summary-stats">
                  <div>
                    <dt>Top ideas count</dt>
                    <dd>{topIdeasCount != null ? topIdeasCount : '—'}</dd>
                  </div>
                  <div>
                    <dt>Eligible setups</dt>
                    <dd>{selected.eligible_count ?? selected.result_count ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Eligible rate</dt>
                    <dd>{formatPct(selectedEligible)}</dd>
                  </div>
                  <div>
                    <dt>Data coverage</dt>
                    <dd>{formatPct(selectedCoverage)}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  className="primary-button scan-history-export-selected"
                  disabled={
                    (selected.status ?? 'completed').toLowerCase() !== 'completed' ||
                    busyId === selected.id ||
                    exportingId === selected.id
                  }
                  onClick={() => void handleExport(selected.id)}
                >
                  {exportingId === selected.id ? 'Exporting…' : 'Export selected CSV'}
                </button>
              </>
            ) : (
              <p className="field-hint">Select a scan row to see its summary.</p>
            )}
          </div>
        </aside>
      </div>

      <footer className="inspect-plan-footer">
        <div className="find-coverage">
          <span>Data coverage</span>
          <div className="find-coverage-bar" aria-hidden="true">
            <i style={{ width: `${Math.max(0, Math.min(100, footerCoverage ?? 0))}%` }} />
          </div>
          <strong>{footerCoverage != null ? `${Math.round(footerCoverage)}%` : '—'}</strong>
        </div>
        <p className="find-footer-disclaimer">Not financial advice. Trading involves risk.</p>
        <div className="find-footer-right">
          <span className="find-footer-asof">
            Data as of {dataAsOf ? formatDateTime(dataAsOf) : '—'}
          </span>
          <button
            type="button"
            className="secondary-button find-tool-btn"
            disabled={refreshing}
            onClick={onRefresh}
          >
            Refresh
          </button>
        </div>
      </footer>
    </section>
  )
}
