/** NSE trading-day helpers for Intraday Desk date selection (IST calendar dates). */

/** Full-day closed + Muhurat (non-ORB) holidays — keep in sync with backend nse_holidays.json. */
const NSE_HOLIDAYS = new Set([
  '2025-02-26',
  '2025-03-14',
  '2025-03-31',
  '2025-04-10',
  '2025-04-14',
  '2025-04-18',
  '2025-05-01',
  '2025-08-15',
  '2025-08-27',
  '2025-10-02',
  '2025-10-21',
  '2025-10-22',
  '2025-11-05',
  '2025-12-25',
  '2026-01-26',
  '2026-03-03',
  '2026-03-26',
  '2026-03-31',
  '2026-04-03',
  '2026-04-14',
  '2026-05-01',
  '2026-05-28',
  '2026-06-26',
  '2026-09-14',
  '2026-10-02',
  '2026-10-20',
  '2026-11-10',
  '2026-11-24',
  '2026-12-25',
])

function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toIsoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function isWeekend(iso: string): boolean {
  const d = parseIsoDate(iso)
  const wd = d.getDay()
  return wd === 0 || wd === 6
}

export function isNseHoliday(iso: string): boolean {
  return NSE_HOLIDAYS.has(iso)
}

export function isTradingDay(iso: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false
  return !isWeekend(iso) && !isNseHoliday(iso)
}

/** Last trading day on or before `iso` (defaults to local today). */
export function lastTradingDayOnOrBefore(iso?: string): string {
  let cur = parseIsoDate(iso || toIsoDate(new Date()))
  for (let i = 0; i < 370; i += 1) {
    const s = toIsoDate(cur)
    if (isTradingDay(s)) return s
    cur.setDate(cur.getDate() - 1)
  }
  return toIsoDate(new Date())
}

export function defaultSessionDate(): string {
  return lastTradingDayOnOrBefore()
}

export function daysInMonth(year: number, monthIndex0: number): number {
  return new Date(year, monthIndex0 + 1, 0).getDate()
}
