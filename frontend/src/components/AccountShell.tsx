import { useCallback, useEffect, useMemo, useState } from 'react'
import { RiskCoachPanel } from './RiskCoachPanel'
import { listScanRuns } from '../scan/api'
import { listIntradaySessions } from '../intraday/api'
import { PAPER_CLAIM } from '../terminology'

type ThemeChoice = 'light' | 'dark' | 'system'
type AccountTab = 'risk' | 'alerts' | 'appearance' | 'export' | 'plans' | 'broker'
type TradingMode = 'paper' | 'broker'

type Props = {
  baseUrl: string
  theme: ThemeChoice
  onThemeChange: (next: ThemeChoice) => void
  accountEquity: string
  riskPercent: string
  onEquityChange: (value: string) => void
  onRiskChange: (value: string) => void
  paperTradingEnabled: boolean
  onPaperEnabledChange: (enabled: boolean) => void
  onOpenCapital: () => void
  swingRefreshSec: string
  intradayRefreshSec: string
  practiceTickMode: string
  onSaveRefresh: (next: {
    swingRefreshSec: string
    intradayRefreshSec: string
    practiceTickMode: string
  }) => void
  initialTab?: AccountTab
}

type AlertPrefs = {
  browser: boolean
  email: boolean
  ses: boolean
  morning: boolean
  eod: boolean
  frequency: string
}

type AuditRow = {
  id: string
  timestamp: string
  event: string
  actor: string
  hash: string
  detail: string
}

const ALERT_KEY = 'tp_alert_prefs_v1'
const BROKER_MODE_KEY = 'tp_trading_mode'
const PLAN_KEY = 'tp_selected_plan'
const BROKER_ACK_KEY = 'tp_broker_ack'

const DEFAULT_ALERTS: AlertPrefs = {
  browser: true,
  email: false,
  ses: false,
  morning: false,
  eod: false,
  frequency: 'daily',
}

const PLANS = [
  { id: 'free', name: 'Free', perks: ['NSE filters'] },
  { id: 'pro', name: 'Pro', perks: ['NSE filters', 'AI briefs'] },
  { id: 'desk', name: 'Desk', perks: ['NSE filters', 'AI briefs', 'Priority support'] },
] as const

function readAlerts(): AlertPrefs {
  try {
    const raw = localStorage.getItem(ALERT_KEY)
    if (!raw) {
      return {
        ...DEFAULT_ALERTS,
        browser: localStorage.getItem('tp_alert_browser') !== '0',
        email: localStorage.getItem('tp_alert_email') === '1',
        frequency: localStorage.getItem('tp_alert_cadence') || 'daily',
      }
    }
    return { ...DEFAULT_ALERTS, ...(JSON.parse(raw) as Partial<AlertPrefs>) }
  } catch {
    return DEFAULT_ALERTS
  }
}

function csvEscape(value: string | number | null | undefined): string {
  const text = value == null ? '' : String(value)
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

function downloadText(filename: string, body: string, mime = 'text/csv;charset=utf-8') {
  const blob = new Blob([body], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function shortHash(input: string): string {
  let h = 2166136261
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0).toString(16).padStart(8, '0').slice(0, 8)
}

function formatApiDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return JSON.stringify(item)
      })
      .join('; ')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return fallback
}

export function AccountShell({
  baseUrl,
  theme,
  onThemeChange,
  accountEquity,
  riskPercent,
  onEquityChange,
  onRiskChange,
  paperTradingEnabled,
  onPaperEnabledChange,
  onOpenCapital,
  swingRefreshSec,
  intradayRefreshSec,
  practiceTickMode,
  onSaveRefresh,
  initialTab = 'risk',
}: Props) {
  const [tab, setTab] = useState<AccountTab>(initialTab)
  const [alerts, setAlerts] = useState<AlertPrefs>(() => readAlerts())
  const [alertNotice, setAlertNotice] = useState('')
  const [draftSwing, setDraftSwing] = useState(swingRefreshSec)
  const [draftIntraday, setDraftIntraday] = useState(intradayRefreshSec)
  const [draftPractice, setDraftPractice] = useState(practiceTickMode)
  const [appearanceNotice, setAppearanceNotice] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState(localStorage.getItem('tp_token') || '')
  const [me, setMe] = useState<Record<string, unknown> | null>(null)
  const [selectedPlan, setSelectedPlan] = useState(() => localStorage.getItem(PLAN_KEY) || 'pro')
  const [authMsg, setAuthMsg] = useState('')
  const [mode, setMode] = useState<TradingMode>(() =>
    localStorage.getItem(BROKER_MODE_KEY) === 'broker' ? 'broker' : 'paper',
  )
  const [brokerAck, setBrokerAck] = useState(() => localStorage.getItem(BROKER_ACK_KEY) === '1')
  const [brokerNotice, setBrokerNotice] = useState('')
  const [auditRows, setAuditRows] = useState<AuditRow[]>([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState('')

  useEffect(() => {
    setDraftSwing(swingRefreshSec)
    setDraftIntraday(intradayRefreshSec)
    setDraftPractice(practiceTickMode)
  }, [swingRefreshSec, intradayRefreshSec, practiceTickMode])

  useEffect(() => {
    localStorage.setItem(ALERT_KEY, JSON.stringify(alerts))
    localStorage.setItem('tp_alert_browser', alerts.browser ? '1' : '0')
    localStorage.setItem('tp_alert_email', alerts.email ? '1' : '0')
    localStorage.setItem('tp_alert_cadence', alerts.frequency)
  }, [alerts])

  const previewSample = useMemo(() => {
    if (alerts.morning) return 'Morning brief — eligible setups ready'
    if (alerts.eod) return 'EOD summary — session closed'
    return 'Eligible setup RELIANCE'
  }, [alerts.morning, alerts.eod])

  const persistAlerts = (patch: Partial<AlertPrefs>) => {
    setAlerts((current) => ({ ...current, ...patch }))
    setAlertNotice('Alert preferences saved on this device.')
  }

  async function requestBrowserPermission() {
    if (!('Notification' in window)) {
      setAlertNotice('Browser notifications are not available in this browser.')
      return
    }
    const permission = await Notification.requestPermission()
    if (permission === 'granted') {
      persistAlerts({ browser: true })
      new Notification('TradePilot', { body: 'Browser alerts enabled for practice.' })
      setAlertNotice('Browser notifications enabled.')
    } else {
      persistAlerts({ browser: false })
      setAlertNotice('Browser notification permission denied.')
    }
  }

  const loadAudit = useCallback(async () => {
    setAuditLoading(true)
    setAuditError('')
    try {
      const rows: AuditRow[] = []
      const scans = await listScanRuns(baseUrl, 20)
      for (const run of scans) {
        const stamp = run.finished_at || run.started_at || ''
        const payload = `scan:${run.id}:${run.status}:${stamp}`
        rows.push({
          id: `scan-${run.id}`,
          timestamp: stamp || '—',
          event: run.status === 'COMPLETED' ? 'Scan complete' : `Scan ${run.status}`,
          actor: 'User',
          hash: shortHash(payload),
          detail: `run=${run.id}; eligible=${run.eligible_count ?? '—'}`,
        })
      }
      const { sessions } = await listIntradaySessions(baseUrl, 12)
      for (const session of sessions) {
        const stamp = session.created_at || session.session_date
        const payload = `session:${session.id}:${session.fill_count}:${stamp}`
        rows.push({
          id: `session-${session.id}`,
          timestamp: stamp,
          event: 'Session closed',
          actor: 'System',
          hash: shortHash(payload),
          detail: `session=${session.id.slice(0, 8)}; fills=${session.fill_count}`,
        })
      }
      const paperRes = await fetch(`${baseUrl}/api/v1/paper/trades?status=ALL`)
      if (paperRes.ok) {
        const body = (await paperRes.json()) as {
          trades?: Array<{ id: number; symbol: string; status: string; closed_at?: string | null; opened_at?: string | null }>
        }
        for (const trade of body.trades || []) {
          const stamp = trade.closed_at || trade.opened_at || ''
          const payload = `practice:${trade.id}:${trade.symbol}:${trade.status}:${stamp}`
          rows.push({
            id: `practice-${trade.id}`,
            timestamp: stamp || '—',
            event: 'Practice trade',
            actor: 'User',
            hash: shortHash(payload),
            detail: `${trade.symbol} · ${trade.status}`,
          })
        }
      }
      rows.sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)))
      setAuditRows(rows)
    } catch (err) {
      setAuditError(err instanceof Error ? err.message : 'Failed to load audit trail')
    } finally {
      setAuditLoading(false)
    }
  }, [baseUrl])

  useEffect(() => {
    if (tab === 'export') void loadAudit()
  }, [tab, loadAudit])

  function exportAuditCsv(rows: AuditRow[], filename: string) {
    const lines = [
      ['Timestamp', 'Event', 'Actor', 'Hash', 'Detail'].map(csvEscape).join(','),
      ...rows.map((row) =>
        [row.timestamp, row.event, row.actor, row.hash, row.detail].map(csvEscape).join(','),
      ),
    ]
    downloadText(filename, lines.join('\n'))
  }

  function downloadAuditPack() {
    const pack = {
      generated_at: new Date().toISOString(),
      claim: 'Informational only — not brokerage advice.',
      sku: 'sellable-audit-pack-v1',
      rows: auditRows,
    }
    downloadText(
      `tradepilot-audit-pack-${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(pack, null, 2),
      'application/json;charset=utf-8',
    )
  }

  async function signup() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, plan: selectedPlan }),
    })
    const body = await res.json()
    if (!res.ok) {
      setAuthMsg(formatApiDetail(body.detail, 'Signup failed'))
      return
    }
    setToken(body.token)
    localStorage.setItem('tp_token', body.token)
    setAuthMsg('Signed up (stub auth)')
  }

  async function login() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const body = await res.json()
    if (!res.ok) {
      setAuthMsg(formatApiDetail(body.detail, 'Login failed'))
      return
    }
    setToken(body.token)
    localStorage.setItem('tp_token', body.token)
    setAuthMsg('Signed in')
  }

  async function loadMe() {
    if (!token) {
      setAuthMsg('Sign in first')
      return
    }
    const res = await fetch(`${baseUrl}/api/v1/product-shell/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) setMe(await res.json())
    else setAuthMsg(formatApiDetail((await res.json()).detail, 'Could not load profile'))
  }

  function choosePlan(id: string) {
    setSelectedPlan(id)
    localStorage.setItem(PLAN_KEY, id)
    setAuthMsg(`Plan set to ${id} (local until billing ships)`)
  }

  function setTradingMode(next: TradingMode) {
    setMode(next)
    localStorage.setItem(BROKER_MODE_KEY, next)
    if (next === 'paper') {
      onPaperEnabledChange(true)
      setBrokerNotice('Paper-only mode — practice stays the default.')
    } else {
      setBrokerNotice('Broker mode selected — connect still requires acknowledgment.')
    }
  }

  function connectBroker() {
    if (!brokerAck || mode !== 'broker') return
    setBrokerNotice('Broker connect is stubbed. No live orders are placed in this build.')
  }

  return (
    <section className="panel account-shell wireframe-account" aria-label="Account settings">
      <header className="header-block account-shell-head">
        <div>
          <p className="eyebrow practice-book-brandline">
            <span className="practice-ico practice-ico-plane" aria-hidden="true" />
            <span>TradePilot</span>
            <span className="practice-brand-sep" aria-hidden="true" />
            <span>Account / Settings</span>
          </p>
          <h1>
            {tab === 'risk' && 'Risk coach'}
            {tab === 'alerts' && 'Alerts'}
            {tab === 'appearance' && 'Appearance & refresh'}
            {tab === 'export' && 'Export & audit'}
            {tab === 'plans' && 'Account & plans'}
            {tab === 'broker' && 'Broker & trading mode'}
          </h1>
          <p className="header-copy">
            {tab === 'risk'
              ? 'Size shares from capital and risk % — engine still owns Entry / Stop.'
              : tab === 'appearance'
                ? 'Choose theme and how often Swing, Intraday, and Practice refresh.'
                : tab === 'alerts'
                  ? 'Choose notification channels and how often briefs are sent.'
                  : 'Manage notifications, theme, exports, plans, and paper vs broker mode.'}
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={onOpenCapital}>
          Your capital ₹
          {new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(Number(accountEquity) || 0)}
        </button>
      </header>

      <div className="account-tabs" role="tablist" aria-label="Account sections">
        {(
          [
            ['risk', 'Risk'],
            ['alerts', 'Alerts'],
            ['appearance', 'Appearance'],
            ['export', 'Export'],
            ['plans', 'Plans'],
            ['broker', 'Broker'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? 'account-tab active' : 'account-tab'}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'risk' ? (
        <div className="account-section">
          <RiskCoachPanel
            accountEquity={accountEquity}
            riskPercent={riskPercent}
            onEquityChange={onEquityChange}
            onRiskChange={onRiskChange}
            embedded
          />
        </div>
      ) : null}

      {tab === 'alerts' ? (
        <div className="account-section alerts-layout">
          <div className="appearance-card alerts-channels-card">
            <h3>Channels</h3>
            <div className="alerts-toggles">
              {(
                [
                  ['browser', 'Browser notify', 'Desktop notifications for practice alerts'],
                  ['email', 'Email', 'Morning / EOD brief delivery'],
                  ['ses', 'SES cadence', 'Ops email cadence when configured'],
                  ['morning', 'Morning brief', 'Include morning scan summary'],
                  ['eod', 'EOD', 'Include end-of-day summary'],
                ] as const
              ).map(([key, label, hint]) => (
                <label key={key} className="account-toggle">
                  <span className="account-toggle-copy">
                    <strong>{label}</strong>
                    <em>{hint}</em>
                  </span>
                  <input
                    type="checkbox"
                    checked={alerts[key]}
                    onChange={(e) => {
                      const checked = e.target.checked
                      if (key === 'browser' && checked) {
                        void requestBrowserPermission()
                        return
                      }
                      persistAlerts({ [key]: checked })
                    }}
                  />
                </label>
              ))}
            </div>
          </div>
          <div className="appearance-card alerts-side-card">
            <h3>Frequency</h3>
            <label className="field">
              <span>Email / SES cadence</span>
              <select
                value={alerts.frequency}
                onChange={(e) => persistAlerts({ frequency: e.target.value })}
              >
                <option value="off">Off</option>
                <option value="daily">Daily</option>
                <option value="weekdays">Weekdays only</option>
              </select>
            </label>
            <div className="alerts-side-summary" role="status">
              <p>
                <strong>Active channels</strong>
              </p>
              <ul>
                <li>{alerts.browser ? 'Browser on' : 'Browser off'}</li>
                <li>{alerts.email ? 'Email on' : 'Email off'}</li>
                <li>{alerts.ses ? 'SES on' : 'SES off'}</li>
                <li>
                  Briefs: {[alerts.morning && 'Morning', alerts.eod && 'EOD'].filter(Boolean).join(' · ') || 'none'}
                </li>
              </ul>
            </div>
            {alertNotice ? <div className="status ok alerts-inline-status">{alertNotice}</div> : null}
          </div>
          <div className="alerts-preview">
            <div className="alerts-preview-head">Preview sample alert</div>
            <div className="alerts-preview-body">
              <strong>{previewSample}</strong>
              <p className="field-hint">
                {alerts.browser ? 'Browser channel on' : 'Browser channel off'}
                {' · '}
                {alerts.email || alerts.ses ? `Email ${alerts.frequency}` : 'Email off'}
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'appearance' ? (
        <div className="account-section appearance-layout">
          <div className="appearance-card">
            <h3>Theme</h3>
            <div className="theme-radios" role="radiogroup" aria-label="Theme">
              {(['light', 'dark', 'system'] as const).map((choice) => (
                <label key={choice} className="account-radio">
                  <input
                    type="radio"
                    name="theme"
                    checked={theme === choice}
                    onChange={() => onThemeChange(choice)}
                  />
                  <span>{choice[0].toUpperCase() + choice.slice(1)}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="appearance-card">
            <h3>Refresh intervals</h3>
            <label className="field">
              <span>Swing scan</span>
              <select value={draftSwing} onChange={(e) => setDraftSwing(e.target.value)}>
                <option value="60">1 min</option>
                <option value="120">2 min</option>
                <option value="300">5 min</option>
                <option value="600">10 min</option>
              </select>
            </label>
            <label className="field">
              <span>Intraday board</span>
              <select value={draftIntraday} onChange={(e) => setDraftIntraday(e.target.value)}>
                <option value="15">15 sec</option>
                <option value="30">30 sec</option>
                <option value="60">1 min</option>
                <option value="120">2 min</option>
              </select>
            </label>
            <label className="field">
              <span>Practice tick</span>
              <select value={draftPractice} onChange={(e) => setDraftPractice(e.target.value)}>
                <option value="manual">Manual</option>
                <option value="15">15 sec</option>
                <option value="30">30 sec</option>
                <option value="60">1 min</option>
              </select>
            </label>
            <div className="appearance-actions">
              <button
                type="button"
                className="primary-button"
                onClick={() => {
                  onSaveRefresh({
                    swingRefreshSec: draftSwing,
                    intradayRefreshSec: draftIntraday,
                    practiceTickMode: draftPractice,
                  })
                  setAppearanceNotice('Refresh preferences saved.')
                }}
              >
                Save
              </button>
              {appearanceNotice ? <div className="status ok">{appearanceNotice}</div> : null}
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'export' ? (
        <div className="account-section">
          {auditError ? <div className="status error">{auditError}</div> : null}
          <div className="table-wrap scan-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Hash</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {auditLoading ? (
                  <tr>
                    <td colSpan={5}>Loading audit trail…</td>
                  </tr>
                ) : auditRows.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      <div className="empty-state">
                        <strong>No audit events yet</strong>
                        <span>Run a scan, close an intraday session, or open a practice trade.</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  auditRows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.timestamp ? new Date(row.timestamp).toLocaleString('en-IN') : '—'}</td>
                      <td>{row.event}</td>
                      <td>{row.actor}</td>
                      <td className="muted-cell">{row.hash}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => exportAuditCsv([row], `tradepilot-audit-${row.hash}.csv`)}
                        >
                          Export CSV
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="export-options">
            <h3>Export options</h3>
            <div className="export-options-actions">
              <button
                type="button"
                className="primary-button"
                disabled={auditRows.length === 0}
                onClick={() =>
                  exportAuditCsv(auditRows, `tradepilot-audit-${new Date().toISOString().slice(0, 10)}.csv`)
                }
              >
                Export CSV
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={auditRows.length === 0}
                onClick={downloadAuditPack}
              >
                Download audit pack
              </button>
            </div>
            <p className="field-hint">Sellable SKU signed audit of scans/sessions.</p>
          </div>
        </div>
      ) : null}

      {tab === 'plans' ? (
        <div className="account-section plans-layout">
          <div className="account-login-card">
            <h3>Account login</h3>
            <label className="field">
              <span>Email</span>
              <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <div className="account-login-actions">
              <button type="button" className="primary-button" onClick={() => void login()}>
                Sign in
              </button>
              <button type="button" className="secondary-button" onClick={() => void signup()}>
                Sign up
              </button>
              <button type="button" className="ghost-btn" onClick={() => void loadMe()}>
                Me
              </button>
            </div>
            {authMsg ? <div className="status">{authMsg}</div> : null}
            {me ? <pre className="research-json">{JSON.stringify(me, null, 2)}</pre> : null}
          </div>
          <div className="account-plans-list">
            {PLANS.map((plan) => (
              <article
                key={plan.id}
                className={`account-plan-card${selectedPlan === plan.id ? ' selected' : ''}`}
              >
                <div className="account-plan-head">
                  <h3>{plan.name}</h3>
                  {selectedPlan === plan.id ? <span className="plan-selected-badge">Selected</span> : null}
                </div>
                <ul>
                  {plan.perks.map((perk) => (
                    <li key={perk}>{perk}</li>
                  ))}
                </ul>
                <button type="button" className="secondary-button" onClick={() => choosePlan(plan.id)}>
                  {selectedPlan === plan.id ? 'Current plan' : `Choose ${plan.name}`}
                </button>
              </article>
            ))}
            <p className="field-hint account-plans-note">Wireframe-only until auth ships.</p>
          </div>
        </div>
      ) : null}

      {tab === 'broker' ? (
        <div className="account-section broker-layout">
          <fieldset className="broker-mode-box">
            <legend>Mode</legend>
            <label className="account-radio broker-mode-option">
              <input
                type="radio"
                name="trading-mode"
                checked={mode === 'paper'}
                onChange={() => setTradingMode('paper')}
              />
              <span>
                <strong>Paper only</strong>
                <span className="field-hint">Simulate trades with no real money at risk.</span>
              </span>
            </label>
            <label className="account-radio broker-mode-option">
              <input
                type="radio"
                name="trading-mode"
                checked={mode === 'broker'}
                onChange={() => setTradingMode('broker')}
              />
              <span>
                <strong>Broker connect</strong>
                <span className="field-hint">Connect a real broker account to execute live trades.</span>
              </span>
            </label>
            {mode === 'broker' ? (
              <div className="broker-warning">
                <span className="practice-ico practice-ico-warn" aria-hidden="true" />
                <span>Connecting a broker never auto-fires ORB/swing without explicit user confirm.</span>
              </div>
            ) : null}
            <button
              type="button"
              className="primary-button"
              disabled={mode !== 'broker' || !brokerAck}
              onClick={connectBroker}
            >
              Connect broker
            </button>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={brokerAck}
                onChange={(e) => {
                  const next = e.target.checked
                  setBrokerAck(next)
                  localStorage.setItem(BROKER_ACK_KEY, next ? '1' : '0')
                }}
              />
              <span>
                I acknowledge that connecting a broker does not auto-fire any trades and all orders require my
                explicit confirmation.
              </span>
            </label>
            <div className="broker-info">
              <span className="practice-ico practice-ico-info" aria-hidden="true" />
              <div>
                <strong>Practice fake money</strong>
                <p className="field-hint">
                  {paperTradingEnabled
                    ? 'Practice trading is on — use the Practice book before connecting a broker.'
                    : 'Turn on practice from the Practice book to test strategies first.'}
                </p>
                <p className="field-hint">{PAPER_CLAIM}</p>
              </div>
            </div>
            {brokerNotice ? <div className="status ok">{brokerNotice}</div> : null}
          </fieldset>
        </div>
      ) : null}

      <footer className="practice-footer-claim">
        <span className="practice-ico practice-ico-shield" aria-hidden="true" />
        <span>
          {tab === 'export'
            ? 'Informational only — not brokerage advice.'
            : 'Practice is not a brokerage order. This is a simulated learning environment.'}
        </span>
      </footer>
    </section>
  )
}
