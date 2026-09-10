import { useCallback, useEffect, useMemo, useState } from 'react'
import { getScanRun, isCompletedScan, listScanRuns, sendBriefEmail } from '../scan/api'
import type { Opportunity, OpportunityScanResponse } from '../scan/types'
import { directionLabel } from '../terminology'

type Props = {
  baseUrl: string
  formatPrice: (value: string | number | null | undefined) => string
  onOpenSwing?: () => void
}

type BriefMode = 'morning' | 'eod'

function coveragePct(scan: OpportunityScanResponse): number | null {
  const scanned = Number(scan.symbols_scanned)
  const eligible = Number(scan.eligible_count)
  if (!Number.isFinite(scanned) || scanned <= 0 || !Number.isFinite(eligible)) return null
  return Math.min(100, Math.round((eligible / scanned) * 100))
}

function topIdeas(scan: OpportunityScanResponse): Opportunity[] {
  const ranked = (scan.top?.length ? scan.top : scan.opportunities) || []
  return ranked.slice(0, 3)
}

function riskBullets(scan: OpportunityScanResponse): string[] {
  const risks: string[] = []
  const forming = Number(scan.forming_count) || 0
  const eligible = Number(scan.eligible_count) || 0
  if (eligible === 0) risks.push('No eligible setups in this scan')
  if (forming > eligible) risks.push('More forming than eligible — patience required')
  const issues = (scan as { issues?: Array<{ severity?: string; message?: string }> }).issues || []
  for (const issue of issues.slice(0, 3)) {
    if (issue.message) risks.push(issue.message)
  }
  if (!risks.length) {
    risks.push('Market volatility can invalidate levels after the scan')
    risks.push('Practice sizing only — never promissory returns')
  }
  return risks
}

function buildPlainBrief(mode: BriefMode, scan: OpportunityScanResponse, formatPrice: Props['formatPrice']): string {
  const label = mode === 'eod' ? 'EOD' : 'Morning'
  const ideas = topIdeas(scan)
  const lines = [
    `${label} brief — ${scan.eligible_count ?? 0} eligible · ${scan.forming_count ?? 0} forming`,
    scan.ai_brief?.trim() || '',
    '',
    'Top ideas:',
    ...ideas.map(
      (op, i) =>
        `${i + 1}. ${op.symbol} ${directionLabel(op.candidate.direction)} · Entry ${formatPrice(op.candidate.entry_price)} · Stop ${formatPrice(op.candidate.stop_loss)}`,
    ),
    '',
    'Risks:',
    ...riskBullets(scan).map((r) => `- ${r}`),
    '',
    'Warning: No promissory returns.',
  ]
  return lines.filter((l, idx, arr) => !(l === '' && arr[idx - 1] === '')).join('\n')
}

/** UC-F5 — in-app brief center from latest completed scan facts. */
export function BriefCenter({ baseUrl, formatPrice, onOpenSwing }: Props) {
  const [mode, setMode] = useState<BriefMode>('morning')
  const [scan, setScan] = useState<OpportunityScanResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [sendError, setSendError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const runs = await listScanRuns(baseUrl, 12)
      const completed = runs.find((r) => (r.status || 'COMPLETED').toUpperCase() === 'COMPLETED')
      if (!completed) {
        setScan(null)
        setError('No completed scan yet. Run Find Setups first.')
        return
      }
      const payload = await getScanRun(baseUrl, completed.id)
      if (!isCompletedScan(payload)) {
        setScan(null)
        setError('Latest scan is still running.')
        return
      }
      setScan(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load brief')
    } finally {
      setLoading(false)
    }
  }, [baseUrl])

  useEffect(() => {
    void load()
  }, [load])

  const ideas = useMemo(() => (scan ? topIdeas(scan) : []), [scan])
  const coverage = scan ? coveragePct(scan) : null
  const risks = useMemo(() => (scan ? riskBullets(scan) : []), [scan])
  const plainText = useMemo(
    () => (scan ? buildPlainBrief(mode, scan, formatPrice) : ''),
    [scan, mode, formatPrice],
  )

  async function copyBrief() {
    if (!plainText) return
    try {
      await navigator.clipboard.writeText(plainText)
      setNotice('Brief copied to clipboard.')
      setSendError('')
    } catch {
      setNotice('Could not copy — select the text manually.')
    }
  }

  async function sendEmail() {
    if (!scan) return
    setSending(true)
    setNotice('')
    setSendError('')
    try {
      const result = await sendBriefEmail(baseUrl, {
        mode,
        scan_run_id: scan.scan_run_id ?? undefined,
      })
      const to =
        result.recipients && result.recipients.length
          ? ` to ${result.recipients.join(', ')}`
          : ''
      const via = result.provider ? ` via ${result.provider.toUpperCase()}` : ''
      setNotice(`Email sent${via}${to}.`)
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'Failed to send email')
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="panel brief-center wireframe-brief" aria-label="Brief center">
      <header className="header-block brief-center-head">
        <p className="eyebrow practice-book-brandline">
          <span className="practice-ico practice-ico-plane" aria-hidden="true" />
          <span>TradePilot</span>
          <span className="practice-brand-sep" aria-hidden="true" />
          <span>Brief</span>
        </p>
        <h1>Brief</h1>
        <p className="header-copy">Grounded from your latest completed scan — no promissory returns.</p>
      </header>

      <div className="brief-tabs" role="tablist" aria-label="Brief type">
        <button
          type="button"
          role="tab"
          className={mode === 'morning' ? 'brief-tab active' : 'brief-tab'}
          aria-selected={mode === 'morning'}
          onClick={() => setMode('morning')}
        >
          Morning brief
        </button>
        <button
          type="button"
          role="tab"
          className={mode === 'eod' ? 'brief-tab active' : 'brief-tab'}
          aria-selected={mode === 'eod'}
          onClick={() => setMode('eod')}
        >
          EOD brief
        </button>
        <button type="button" className="secondary-button" onClick={() => void load()} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error ? (
        <div className="empty-state">
          <strong>{error}</strong>
          {onOpenSwing ? (
            <button type="button" className="secondary-button" onClick={onOpenSwing}>
              Open Find Setups
            </button>
          ) : null}
        </div>
      ) : null}

      {scan ? (
        <>
          <article className="brief-block">
            <h3>Top 3 ideas</h3>
            {ideas.length === 0 ? (
              <p className="field-hint">No top ideas in this scan.</p>
            ) : (
              <ul className="brief-idea-list">
                {ideas.map((op, index) => (
                  <li key={op.symbol}>
                    <strong>
                      {index + 1}. {op.symbol}
                    </strong>
                    <span>
                      {directionLabel(op.candidate.direction)} · Entry{' '}
                      {formatPrice(op.candidate.entry_price)} · Stop {formatPrice(op.candidate.stop_loss)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {scan.ai_brief ? <p className="brief-ai-text">{scan.ai_brief}</p> : null}
          </article>

          <article className="brief-block">
            <h3>Coverage %</h3>
            <div className="brief-coverage" aria-label={`Coverage ${coverage ?? 0} percent`}>
              <div className="brief-coverage-bars">
                {[20, 35, 50, 65, 80].map((h, i) => (
                  <span
                    key={h}
                    className={`brief-bar${coverage != null && coverage >= h - 5 ? ' is-hot' : ''}`}
                    style={{ height: `${h}%` }}
                    aria-hidden="true"
                  />
                ))}
              </div>
              <strong>{coverage != null ? `${coverage}%` : '—'}</strong>
            </div>
            <p className="field-hint">
              Eligible {scan.eligible_count ?? 0} of {scan.symbols_scanned ?? '—'} scanned
            </p>
          </article>

          <article className="brief-block">
            <h3>Risks</h3>
            <ul>
              {risks.map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ul>
          </article>

          <div className="brief-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void sendEmail()}
              disabled={sending || loading}
            >
              {sending ? 'Sending…' : 'Send email'}
            </button>
            <button type="button" className="primary-button" onClick={() => void copyBrief()}>
              Copy
            </button>
          </div>

          <div className="brief-warning" role="note">
            <span className="coach-ico coach-ico-warn" aria-hidden="true" />
            Warning: No promissory returns.
          </div>
        </>
      ) : null}

      {sendError ? <div className="status error">{sendError}</div> : null}
      {notice ? <div className="status ok">{notice}</div> : null}
      <p className="brief-disclaimer">TradePilot can make mistakes. Always do your own analysis.</p>
    </section>
  )
}
