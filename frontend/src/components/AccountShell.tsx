import { useState } from 'react'

type Props = {
  baseUrl: string
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

export function AccountShell({ baseUrl }: Props) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState(localStorage.getItem('tp_token') || '')
  const [me, setMe] = useState<Record<string, unknown> | null>(null)
  const [plans, setPlans] = useState<unknown[]>([])
  const [legal, setLegal] = useState<Record<string, string> | null>(null)
  const [msg, setMsg] = useState('')

  async function signup() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, plan: 'free' }),
    })
    const body = await res.json()
    if (!res.ok) {
      setMsg(formatApiDetail(body.detail, 'Signup failed'))
      return
    }
    setToken(body.token)
    localStorage.setItem('tp_token', body.token)
    setMsg('Signed up (stub auth)')
  }

  async function login() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const body = await res.json()
    if (!res.ok) {
      setMsg(formatApiDetail(body.detail, 'Login failed'))
      return
    }
    setToken(body.token)
    localStorage.setItem('tp_token', body.token)
    setMsg('Logged in')
  }

  async function loadMe() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) setMe(await res.json())
    else setMsg(formatApiDetail((await res.json()).detail, 'Could not load profile'))
  }

  async function loadPlans() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/plans`)
    if (res.ok) {
      const body = await res.json()
      setPlans(body.plans || [])
    }
  }

  async function loadLegal() {
    const res = await fetch(`${baseUrl}/api/v1/product-shell/legal/disclosures`)
    if (res.ok) setLegal(await res.json())
  }

  return (
    <section className="panel account-shell">
      <header className="header-block">
        <p className="eyebrow">Account</p>
        <h1>Plans & disclosures</h1>
        <p className="field-hint">Sellable shell (EP8 stub) — Razorpay/IdP wire-up before charging customers.</p>
      </header>
      <div className="intraday-controls">
        <label className="field">
          <span>Email</span>
          <input value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button type="button" className="primary-button" onClick={() => void signup()}>
          Sign up
        </button>
        <button type="button" className="secondary-button" onClick={() => void login()}>
          Log in
        </button>
        <button type="button" className="secondary-button" onClick={() => void loadMe()}>
          Me
        </button>
        <button type="button" className="secondary-button" onClick={() => void loadPlans()}>
          Plans
        </button>
        <button type="button" className="secondary-button" onClick={() => void loadLegal()}>
          Legal
        </button>
      </div>
      {msg && <div className="status">{msg}</div>}
      {me && <pre className="research-json">{JSON.stringify(me, null, 2)}</pre>}
      {plans.length > 0 && <pre className="research-json">{JSON.stringify(plans, null, 2)}</pre>}
      {legal && (
        <ul className="intraday-how-steps">
          {Object.entries(legal).map(([k, v]) => (
            <li key={k}>
              <strong>{k}</strong> — {v}
            </li>
          ))}
        </ul>
      )}
      <div className="alerts-settings">
        <h3>Alert preferences</h3>
        <p className="field-hint">Browser + email cadence (stored locally until account sync).</p>
        <label className="field">
          <input
            type="checkbox"
            defaultChecked={localStorage.getItem('tp_alert_browser') !== '0'}
            onChange={(e) => localStorage.setItem('tp_alert_browser', e.target.checked ? '1' : '0')}
          />
          Browser notifications for practice alerts
        </label>
        <label className="field">
          <input
            type="checkbox"
            defaultChecked={localStorage.getItem('tp_alert_email') === '1'}
            onChange={(e) => localStorage.setItem('tp_alert_email', e.target.checked ? '1' : '0')}
          />
          Email morning / EOD briefs
        </label>
        <label className="field">
          <span>Cadence</span>
          <select
            defaultValue={localStorage.getItem('tp_alert_cadence') || 'daily'}
            onChange={(e) => localStorage.setItem('tp_alert_cadence', e.target.value)}
          >
            <option value="off">Off</option>
            <option value="daily">Daily</option>
            <option value="weekdays">Weekdays only</option>
          </select>
        </label>
      </div>
    </section>
  )
}
