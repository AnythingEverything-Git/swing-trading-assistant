import { useCallback, useEffect, useState } from 'react'

export type SchedulerJob = {
  job_id: string
  label: string
  source: string
  enabled: boolean
  schedule: string
  universe: string | null
  running: boolean
  next_run_at: string | null
  last_started_at: string | null
  last_finished_at: string | null
  last_status: string
  last_detail: string | null
  phase: string | null
  can_run: boolean
  progress_done: number | null
  progress_total: number | null
  progress_current: string | null
  progress_pct: number | null
}

export type SchedulerStatusPayload = {
  environment: string
  data_source: string
  live_ready: boolean
  upstox_token_configured: boolean
  refresh_mutex_held: boolean
  history_backfill_running?: boolean
  last_candle_time: string | null
  last_1m_candle_time: string | null
  symbols_with_candles: number
  symbols_with_1m: number
  stale_risk: string
  jobs: SchedulerJob[]
}

export type ReadinessGate = {
  id: string
  label: string
  status: string
  detail: string
  metrics?: Record<string, unknown>
}

export type ReadinessPayload = {
  universe: string
  ready: boolean
  status: string
  as_of: string
  provider_1d_max: string | null
  calendar_1d_expected: string | null
  gates: ReadinessGate[]
  recommendations: string[]
}

type Props = {
  baseUrl: string
}

function formatTs(value: string | null | undefined): string {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value))
  } catch {
    return value
  }
}

function pillClass(job: SchedulerJob): string {
  if (!job.enabled) return 'status-pill closed'
  if (job.running || job.last_status === 'running') return 'status-pill open'
  if (job.last_status === 'failed') return 'status-pill pending'
  if (job.last_status === 'ok') return 'status-pill open'
  if (job.last_status === 'skipped') return 'status-pill closed'
  return 'status-pill closed'
}

function pillLabel(job: SchedulerJob): string {
  if (!job.enabled) return 'Disabled'
  if (job.running || job.last_status === 'running') return 'Running'
  if (job.last_status === 'failed') return 'Failed'
  if (job.last_status === 'ok') return 'Idle'
  if (job.last_status === 'skipped') return 'Skipped'
  return 'Unknown'
}

function progressLabel(job: SchedulerJob): string | null {
  if (job.progress_done == null || job.progress_total == null || job.progress_total <= 0) {
    return null
  }
  const pct = job.progress_pct ?? Math.round((100 * job.progress_done) / job.progress_total)
  const current = job.progress_current ? ` · ${job.progress_current}` : ''
  return `${job.progress_done}/${job.progress_total} (${pct}%)${current}`
}

function readinessPillClass(status: string): string {
  if (status === 'green') return 'status-pill open'
  if (status === 'amber') return 'status-pill pending'
  if (status === 'skipped') return 'status-pill closed'
  return 'status-pill pending'
}

export function SchedulerOpsPanel({ baseUrl }: Props) {
  const [payload, setPayload] = useState<SchedulerStatusPayload | null>(null)
  const [readiness, setReadiness] = useState<ReadinessPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyJobId, setBusyJobId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [schedulersResp, readinessResp] = await Promise.all([
        fetch(`${baseUrl}/api/v1/ops/schedulers`),
        fetch(`${baseUrl}/api/v1/ops/readiness?universe=NIFTY_500`),
      ])
      if (!schedulersResp.ok) {
        throw new Error(`HTTP ${schedulersResp.status}`)
      }
      const data = (await schedulersResp.json()) as SchedulerStatusPayload
      setPayload(data)
      if (readinessResp.ok) {
        setReadiness((await readinessResp.json()) as ReadinessPayload)
      } else {
        setReadiness(null)
      }
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scheduler status')
    } finally {
      setLoading(false)
    }
  }, [baseUrl])

  const historyJob = payload?.jobs.find((j) => j.job_id === 'host_1m_history')
  const historyRunning = Boolean(
    payload?.history_backfill_running || historyJob?.running || historyJob?.last_status === 'running',
  )

  useEffect(() => {
    void load()
    const intervalMs = historyRunning ? 5_000 : 15_000
    const id = window.setInterval(() => {
      void load()
    }, intervalMs)
    return () => window.clearInterval(id)
  }, [load, historyRunning])

  const setEnabled = async (job: SchedulerJob, enabled: boolean) => {
    setBusyJobId(job.job_id)
    setActionError(null)
    try {
      const response = await fetch(`${baseUrl}/api/v1/ops/schedulers/${job.job_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(
          typeof body?.detail === 'string' ? body.detail : `Enable/disable failed (${response.status})`,
        )
      }
      await load()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Enable/disable failed')
    } finally {
      setBusyJobId(null)
    }
  }

  const runNow = async (job: SchedulerJob, body?: Record<string, unknown>) => {
    if (!job.can_run) return
    setBusyJobId(job.job_id)
    setActionError(null)
    try {
      const response = await fetch(`${baseUrl}/api/v1/ops/schedulers/${job.job_id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body ?? {}),
      })
      if (!response.ok) {
        const respBody = await response.json().catch(() => null)
        const detail = respBody?.detail
        throw new Error(typeof detail === 'string' ? detail : `Run failed (${response.status})`)
      }
      await load()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Run failed')
    } finally {
      setBusyJobId(null)
    }
  }

  return (
    <div className="account-section scheduler-ops-panel">
      <div className="appearance-card">
        <div className="scheduler-ops-head">
          <h3>Live schedulers</h3>
          <button type="button" className="secondary-button" onClick={() => void load()}>
            Refresh
          </button>
        </div>
        <p className="header-copy">
          Enable/disable jobs and start them manually. Prefer the ephemeral worker for staged 1m history (Nifty 50 →
          100 remaining → 500 remaining) so the live API stays healthy. Tiny stages via Ops are OK; avoid NSE_ALL on
          this Free Tier box. Polls every {historyRunning ? '5' : '15'}s while a backfill is running.
        </p>
        <div className="scheduler-n500-checklist" aria-label="Nifty 500 session checklist">
          <strong>Nifty 500 session checklist</strong>
          <ul>
            <li>Upstox token valid · live_ready</li>
            <li>1d at provider-max (≥99% N500) — paced retry 17:00 if behind</li>
            <li>Today 1m for NIFTY_500 after ~09:25 (cron or perfect-today)</li>
            <li>In-app 1m light: NIFTY_50 / limit 50 / 600s (not NSE_ALL)</li>
            <li>Intraday desk universe = NIFTY_500 · persisted</li>
          </ul>
        </div>
        {readiness ? (
          <div className="scheduler-readiness" aria-label="Nifty 500 readiness">
            <div className="scheduler-ops-head">
              <div>
                <h3>
                  Nifty 500 readiness{' '}
                  <span className={readinessPillClass(readiness.status)}>
                    {readiness.status}
                  </span>
                </h3>
                <p className="header-copy">
                  ready={String(readiness.ready)} · provider_1d_max {formatTs(readiness.provider_1d_max)}
                  {readiness.calendar_1d_expected
                    ? ` · calendar expect ${readiness.calendar_1d_expected}`
                    : ''}
                  . Amber = Upstox publish lag (aligned to provider-max). Red = our lag / token / host.
                </p>
              </div>
            </div>
            <div className="scheduler-ops-strip scheduler-readiness-gates" aria-label="Readiness gates">
              {readiness.gates.map((gate) => (
                <span key={gate.id} title={gate.detail}>
                  {gate.id}{' '}
                  <span className={readinessPillClass(gate.status)}>{gate.status}</span>
                </span>
              ))}
            </div>
            {readiness.recommendations.length > 0 ? (
              <ul className="scheduler-readiness-recs">
                {readiness.recommendations.slice(0, 4).map((rec) => (
                  <li key={rec}>{rec}</li>
                ))}
              </ul>
            ) : null}
            <p className="muted">
              Manual recovery: <code>ops/vps/run_1d_n500_paced.sh</code> ·{' '}
              <code>run_1m_today.sh</code> · watchdog restarts api on /health fail
            </p>
          </div>
        ) : null}
        {loading && !payload ? <p className="muted">Loading…</p> : null}
        {error ? <p className="error-text">Could not load status: {error}</p> : null}
        {actionError ? <p className="error-text">{actionError}</p> : null}
        {payload ? (
          <>
            <div className="scheduler-ops-strip" aria-label="Data freshness">
              <span>
                Source <strong>{payload.data_source}</strong>
              </span>
              <span>
                Live{' '}
                <span className={`status-pill ${payload.live_ready ? 'open' : 'closed'}`}>
                  {payload.live_ready ? 'ready' : 'not ready'}
                </span>
              </span>
              <span>
                Stale{' '}
                <span className="status-pill pending">{payload.stale_risk}</span>
              </span>
              <span>
                1d {formatTs(payload.last_candle_time)} ({payload.symbols_with_candles})
              </span>
              <span>
                1m {formatTs(payload.last_1m_candle_time)} ({payload.symbols_with_1m})
              </span>
              <span>
                Mutex{' '}
                <span className={`status-pill ${payload.refresh_mutex_held ? 'open' : 'closed'}`}>
                  {payload.refresh_mutex_held ? 'held' : 'free'}
                </span>
              </span>
              <span>
                History{' '}
                <span className={`status-pill ${historyRunning ? 'open' : 'closed'}`}>
                  {historyRunning ? 'backfilling' : 'idle'}
                </span>
              </span>
            </div>

            {historyJob ? (
              <div className="scheduler-backfill-card" aria-label="1m history backfill">
                <div className="scheduler-ops-head">
                  <div>
                    <h3>Staged 1m history (RVOL)</h3>
                    <p className="header-copy">
                      ~28 calendar days of 1m bars for RVOL lookback (14 sessions). Prefer worker CLI for Free Tier
                      safety; these buttons queue on the live API (fine for Nifty 50 only).
                    </p>
                  </div>
                </div>
                <div className="scheduler-stage-actions">
                  {(
                    [
                      { stage: 'NIFTY_50', label: 'Nifty 50' },
                      { stage: 'NIFTY_100_REMAINING', label: '100 remaining' },
                      { stage: 'NIFTY_500_REMAINING', label: '500 remaining' },
                    ] as const
                  ).map(({ stage, label }) => (
                    <button
                      key={stage}
                      type="button"
                      className="primary-button"
                      disabled={
                        busyJobId === historyJob.job_id ||
                        !historyJob.enabled ||
                        !historyJob.can_run ||
                        historyRunning
                      }
                      onClick={() =>
                        void runNow(historyJob, {
                          stage,
                          universe: stage,
                          lookback_days: 28,
                        })
                      }
                    >
                      {historyRunning ? 'Running…' : label}
                    </button>
                  ))}
                </div>
                {progressLabel(historyJob) || historyJob.last_detail ? (
                  <div className="scheduler-backfill-progress">
                    {historyJob.progress_pct != null && historyJob.progress_total ? (
                      <div
                        className="scheduler-progress-bar"
                        role="progressbar"
                        aria-valuenow={historyJob.progress_pct}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <div
                          className="scheduler-progress-bar-fill"
                          style={{ width: `${Math.min(100, Math.max(0, historyJob.progress_pct))}%` }}
                        />
                      </div>
                    ) : null}
                    <p className="scheduler-job-detail">
                      {progressLabel(historyJob) || historyJob.last_detail}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="table-wrap">
              <table className="data-table scheduler-ops-table">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Status</th>
                    <th>Schedule</th>
                    <th>Universe</th>
                    <th>Progress</th>
                    <th>Last run</th>
                    <th>Detail</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.jobs.map((job) => {
                    const busy = busyJobId === job.job_id
                    const running = job.running || job.last_status === 'running'
                    const mutexBlocked =
                      job.job_id !== 'host_1m_history' && payload.refresh_mutex_held
                    return (
                      <tr key={job.job_id}>
                        <td>
                          <div className="scheduler-job-label">{job.label}</div>
                          <div className="muted scheduler-job-meta">
                            {job.source}
                            {job.phase ? ` · ${job.phase}` : ''}
                          </div>
                        </td>
                        <td>
                          <span className={pillClass(job)}>{pillLabel(job)}</span>
                        </td>
                        <td>{job.schedule || '—'}</td>
                        <td>{job.universe || '—'}</td>
                        <td className="scheduler-job-detail">{progressLabel(job) || '—'}</td>
                        <td>{formatTs(job.last_finished_at || job.last_started_at)}</td>
                        <td className="scheduler-job-detail">{job.last_detail || '—'}</td>
                        <td>
                          <div className="scheduler-job-actions">
                            <button
                              type="button"
                              className="secondary-button"
                              disabled={busy}
                              onClick={() => void setEnabled(job, !job.enabled)}
                            >
                              {job.enabled ? 'Disable' : 'Enable'}
                            </button>
                            <button
                              type="button"
                              className="primary-button"
                              disabled={
                                busy || !job.can_run || !job.enabled || running || mutexBlocked
                              }
                              title={
                                !job.can_run
                                  ? 'Host-only job — run via VPS script'
                                  : !job.enabled
                                    ? 'Enable the job first'
                                    : mutexBlocked
                                      ? 'Another refresh is running'
                                      : 'Start now'
                              }
                              onClick={() =>
                                void runNow(
                                  job,
                                  job.job_id === 'host_1m_history'
                                    ? { stage: 'NIFTY_50', universe: 'NIFTY_50', lookback_days: 28 }
                                    : {},
                                )
                              }
                            >
                              Run now
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
