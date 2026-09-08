import type { ReactNode } from 'react'

export const AUTO_REFRESH_OPTIONS = [
  { value: '30', label: 'Every 30 sec' },
  { value: '60', label: 'Every 1 min' },
  { value: '120', label: 'Every 2 min' },
  { value: '300', label: 'Every 5 min' },
  { value: '600', label: 'Every 10 min' },
] as const

export function formatCountdown(totalSeconds: number | null): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds)) return '—'
  const secs = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

type Props = {
  enabled: boolean
  onEnabledChange: (next: boolean) => void
  intervalSec: string
  onIntervalChange: (next: string) => void
  secondsLeft: number | null
  paused: boolean
  pauseReason: string | null
  refreshing: boolean
  disabled?: boolean
}

export function AutoRefreshBar({
  enabled,
  onEnabledChange,
  intervalSec,
  onIntervalChange,
  secondsLeft,
  paused,
  pauseReason,
  refreshing,
  disabled = false,
}: Props): ReactNode {
  const statusLabel = !enabled
    ? 'Auto-refresh OFF'
    : refreshing
      ? 'Refreshing…'
      : paused
        ? 'Auto-refresh paused'
        : 'Auto-refresh ON'

  return (
    <div
      className={`auto-refresh-bar ${enabled ? 'is-on' : 'is-off'} ${paused && enabled ? 'is-paused' : ''}`}
      role="group"
      aria-label="Auto-refresh scan"
    >
      <label className="auto-refresh-toggle">
        <input
          type="checkbox"
          checked={enabled}
          disabled={disabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
        />
        <span className="auto-refresh-switch" aria-hidden="true" />
        <strong>{statusLabel}</strong>
      </label>

      <label className="auto-refresh-interval">
        <span className="visually-hidden">Refresh interval</span>
        <select
          value={intervalSec}
          disabled={disabled || !enabled}
          onChange={(event) => onIntervalChange(event.target.value)}
          aria-label="Refresh interval"
        >
          {AUTO_REFRESH_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <span className="auto-refresh-countdown" aria-live="polite">
        {enabled
          ? refreshing
            ? 'Scan in progress'
            : paused
              ? pauseReason || 'Paused'
              : `Next refresh in ${formatCountdown(secondsLeft)}`
          : 'Turn on to keep results current'}
      </span>

      <span className="auto-refresh-hint">Pauses when criteria panel open</span>
    </div>
  )
}
