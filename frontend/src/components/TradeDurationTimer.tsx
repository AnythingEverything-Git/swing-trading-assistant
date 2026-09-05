import React, { useEffect, useState } from 'react'

type Props = {
  startedAt: string
  className?: string
  label?: string
}

function formatElapsed(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const totalSec = Math.floor(ms / 1000)
  const days = Math.floor(totalSec / 86400)
  const hours = Math.floor((totalSec % 86400) / 3600)
  const minutes = Math.floor((totalSec % 3600) / 60)
  const seconds = totalSec % 60
  if (days > 0) return `${days}d ${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

/** Live elapsed timer from an ISO start timestamp. */
export function TradeDurationTimer({ startedAt, className = '', label = 'Open for' }: Props) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const started = new Date(startedAt).getTime()
  const text = Number.isFinite(started) ? formatElapsed(now - started) : '—'

  return (
    <span className={`trade-duration-timer ${className}`.trim()} title="Time since this practice trade opened">
      {label ? <span className="trade-duration-label">{label}</span> : null}
      <strong className="trade-duration-digits" aria-live="off">
        {text}
      </strong>
      <span className="trade-duration-pulse" aria-hidden="true" />
    </span>
  )
}
