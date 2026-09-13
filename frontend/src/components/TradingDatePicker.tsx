/** Custom date picker that disables weekends and NSE holidays. */

import { useEffect, useRef, useState } from 'react'
import {
  daysInMonth,
  defaultSessionDate,
  isTradingDay,
  lastTradingDayOnOrBefore,
  toIsoDate,
} from '../intraday/tradingCalendar'

type Props = {
  value: string
  onChange: (iso: string) => void
  maxIso?: string
}

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

export function TradingDatePicker({ value, onChange, maxIso }: Props) {
  const max = maxIso || defaultSessionDate()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = isTradingDay(value) ? value : lastTradingDayOnOrBefore(value || max)
  const [view, setView] = useState(() => {
    const [y, m] = selected.split('-').map(Number)
    return { year: y, month: m - 1 }
  })

  useEffect(() => {
    if (!isTradingDay(value)) {
      onChange(lastTradingDayOnOrBefore(value || max))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- snap invalid defaults once when value is bad
  }, [])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const firstDow = (() => {
    const d = new Date(view.year, view.month, 1)
    // Convert JS Sunday=0 to Monday-first index
    return (d.getDay() + 6) % 7
  })()
  const count = daysInMonth(view.year, view.month)
  const cells: Array<{ iso: string | null; label: string; disabled: boolean }> = []
  for (let i = 0; i < firstDow; i += 1) {
    cells.push({ iso: null, label: '', disabled: true })
  }
  for (let day = 1; day <= count; day += 1) {
    const iso = toIsoDate(new Date(view.year, view.month, day))
    const disabled = !isTradingDay(iso) || iso > max
    cells.push({ iso, label: String(day), disabled })
  }

  function shiftMonth(delta: number) {
    const d = new Date(view.year, view.month + delta, 1)
    setView({ year: d.getFullYear(), month: d.getMonth() })
  }

  return (
    <div className="trading-date-picker" ref={rootRef}>
      <button
        type="button"
        className="trading-date-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          const [y, m] = selected.split('-').map(Number)
          setView({ year: y, month: m - 1 })
          setOpen((v) => !v)
        }}
      >
        {selected}
      </button>
      {open ? (
        <div className="trading-date-popover" role="dialog" aria-label="Trading day">
          <div className="trading-date-nav">
            <button type="button" className="ghost-btn" onClick={() => shiftMonth(-1)} aria-label="Previous month">
              ‹
            </button>
            <strong>
              {new Date(view.year, view.month, 1).toLocaleString(undefined, {
                month: 'short',
                year: 'numeric',
              })}
            </strong>
            <button type="button" className="ghost-btn" onClick={() => shiftMonth(1)} aria-label="Next month">
              ›
            </button>
          </div>
          <div className="trading-date-grid">
            {WEEKDAYS.map((w) => (
              <span key={w} className="trading-date-dow">
                {w}
              </span>
            ))}
            {cells.map((cell, idx) =>
              cell.iso ? (
                <button
                  key={cell.iso}
                  type="button"
                  className={`trading-date-day${cell.iso === selected ? ' is-selected' : ''}${
                    cell.disabled ? ' is-disabled' : ''
                  }`}
                  disabled={cell.disabled}
                  onClick={() => {
                    if (!cell.iso || cell.disabled) return
                    onChange(cell.iso)
                    setOpen(false)
                  }}
                >
                  {cell.label}
                </button>
              ) : (
                <span key={`e-${idx}`} className="trading-date-empty" />
              ),
            )}
          </div>
          <p className="field-hint trading-date-hint">Weekends and NSE holidays are disabled.</p>
        </div>
      ) : null}
    </div>
  )
}
