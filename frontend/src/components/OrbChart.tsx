import { useEffect, useRef } from 'react'
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts'
import type { ChartCandle } from './SetupChart'

export type OrbChartLevels = {
  orHigh?: string | number | null
  orLow?: string | number | null
  entry?: string | number | null
  stop?: string | number | null
  exit?: string | number | null
  triggerIndex?: number | null
}

function num(value: string | number | null | undefined): number | null {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Intraday ORB chart: opening-range band + safety exit (no profit goal line). */
export function OrbChart({ candles, levels }: { candles: ChartCandle[]; levels: OrbChartLevels }) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!hostRef.current || candles.length === 0) return
    const chart = createChart(hostRef.current, {
      width: hostRef.current.clientWidth || 860,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(148, 163, 184, 0.15)' },
        horzLines: { color: 'rgba(148, 163, 184, 0.15)' },
      },
      rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.3)' },
      timeScale: {
        borderColor: 'rgba(148, 163, 184, 0.3)',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: CrosshairMode.Normal },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#16a34a',
      downColor: '#dc2626',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
    })
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
      color: 'rgba(71, 85, 105, 0.45)',
    })
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.7, bottom: 0 },
      borderVisible: false,
    })

    const priceData = candles
      .map((item) => {
        const open = num(item.open)
        const high = num(item.high)
        const low = num(item.low)
        const close = num(item.close)
        if (open == null || high == null || low == null || close == null) return null
        return {
          time: Math.floor(new Date(item.timestamp).getTime() / 1000) as UTCTimestamp,
          open,
          high,
          low,
          close,
        }
      })
      .filter(
        (item): item is { time: UTCTimestamp; open: number; high: number; low: number; close: number } =>
          item !== null,
      )

    candleSeries.setData(priceData)

    if (
      typeof levels.triggerIndex === 'number' &&
      levels.triggerIndex >= 0 &&
      levels.triggerIndex < candles.length
    ) {
      candleSeries.setMarkers([
        {
          time: Math.floor(new Date(candles[levels.triggerIndex].timestamp).getTime() / 1000) as UTCTimestamp,
          position: 'aboveBar',
          color: '#0f766e',
          shape: 'arrowUp',
          text: 'Entry',
        },
      ])
    }

    volumeSeries.setData(
      candles
        .map((item) => {
          const close = num(item.close)
          const open = num(item.open)
          const volume = item.volume == null ? null : Number(item.volume)
          if (close == null || open == null || volume == null || Number.isNaN(volume)) return null
          return {
            time: Math.floor(new Date(item.timestamp).getTime() / 1000) as UTCTimestamp,
            value: volume,
            color: close >= open ? 'rgba(22, 163, 74, 0.35)' : 'rgba(220, 38, 38, 0.35)',
          }
        })
        .filter((item): item is { time: UTCTimestamp; value: number; color: string } => item !== null),
    )

    const addLine = (price: string | number | null | undefined, title: string, color: string, style = LineStyle.Dashed) => {
      const p = num(price)
      if (p == null) return
      candleSeries.createPriceLine({
        price: p,
        title,
        color,
        lineWidth: 1,
        axisLabelVisible: true,
        lineStyle: style,
      })
    }

    addLine(levels.orHigh, 'OR high', '#0f766e', LineStyle.Solid)
    addLine(levels.orLow, 'OR low', '#c2410c', LineStyle.Solid)
    addLine(levels.entry, 'Buy/sell', '#16a34a')
    addLine(levels.stop, 'Safety', '#dc2626')
    addLine(levels.exit, 'Exit', '#64748b')

    chart.timeScale().fitContent()
    const observer = new ResizeObserver(() => {
      if (!hostRef.current) return
      chart.applyOptions({ width: hostRef.current.clientWidth })
    })
    observer.observe(hostRef.current)
    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [candles, levels])

  if (candles.length === 0) {
    return <p className="field-hint">No 1-minute candles for this session.</p>
  }

  return (
    <div
      className="setup-chart orb-chart"
      role="img"
      aria-label="Opening range breakout chart"
      style={{ ['--setup-chart-height' as string]: '320px' }}
    >
      <div className="setup-chart-host" ref={hostRef} />
    </div>
  )
}
