import React, { useEffect, useRef, useState } from 'react'

type Props = {
  value: string | number | null | undefined
  formatted: string
  className?: string
}

/** Renders a live market value with a short up/down flash on change. */
export function LiveValue({ value, formatted, className = '' }: Props) {
  const previous = useRef<number | null>(null)
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    const numeric = value == null || value === '' ? null : Number(value)
    if (numeric == null || !Number.isFinite(numeric)) {
      previous.current = null
      return
    }
    if (previous.current != null && numeric !== previous.current) {
      setFlash(numeric > previous.current ? 'up' : 'down')
      const timer = window.setTimeout(() => setFlash(null), 650)
      previous.current = numeric
      return () => window.clearTimeout(timer)
    }
    previous.current = numeric
  }, [value])

  return (
    <span className={`live-tick ${flash ? `flash-${flash}` : ''} ${className}`.trim()}>
      {formatted}
    </span>
  )
}
