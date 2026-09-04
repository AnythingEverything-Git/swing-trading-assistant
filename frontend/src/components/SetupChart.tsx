import React, { useEffect, useRef } from 'react'
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts'

export type ChartCandle = {
  timestamp: string
  open: string | number
  high: string | number
  low: string | number
  close: string | number
  volume?: number | null
}

type Levels = {
  resistance?: string | number | null
  support?: string | number | null
  entry?: string | number | null
  stop?: string | number | null
  target?: string | number | null
  breakoutIndex?: number | null
  retestIndex?: number | null
  confirmationIndex?: number | null
}

function num(value: string | number | null | undefined): number | null {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function SetupChart({
  candles,
  levels,
}: {
  candles: ChartCandle[]
  levels: Levels
}) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!hostRef.current || candles.length === 0) return
    const chart = createChart(hostRef.current, {
      width: hostRef.current.clientWidth || 860,
      height: 360,
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
      .filter((item): item is { time: UTCTimestamp; open: number; high: number; low: number; close: number } => item !== null)

    candleSeries.setData(priceData)
    const toTime = (timestamp: string) => Math.floor(new Date(timestamp).getTime() / 1000) as UTCTimestamp

    // Small visual anchors for the strategy evidence bars.
    const markers: Array<{
      time: UTCTimestamp
      position: 'aboveBar' | 'belowBar'
      color: string
      shape: 'circle' | 'arrowUp' | 'arrowDown' | 'square'
      text: string
    }> = []
    if (typeof levels.breakoutIndex === 'number' && levels.breakoutIndex >= 0 && levels.breakoutIndex < candles.length) {
      markers.push({
        time: toTime(candles[levels.breakoutIndex].timestamp),
        position: 'aboveBar',
        color: '#7c3aed',
        shape: 'circle',
        text: 'B',
      })
    }
    if (typeof levels.retestIndex === 'number' && levels.retestIndex >= 0 && levels.retestIndex < candles.length) {
      markers.push({
        time: toTime(candles[levels.retestIndex].timestamp),
        position: 'belowBar',
        color: '#f59e0b',
        shape: 'circle',
        text: 'R',
      })
    }
    if (typeof levels.confirmationIndex === 'number' && levels.confirmationIndex >= 0 && levels.confirmationIndex < candles.length) {
      markers.push({
        time: toTime(candles[levels.confirmationIndex].timestamp),
        position: 'aboveBar',
        color: '#0ea5e9',
        shape: 'circle',
        text: 'C',
      })
    }
    if (markers.length > 0) {
      candleSeries.setMarkers(markers)
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

    const addLine = (price: string | number | null | undefined, title: string, color: string) => {
      const p = num(price)
      if (p == null) return
      candleSeries.createPriceLine({
        price: p,
        title,
        color,
        lineWidth: 1,
        axisLabelVisible: true,
        lineStyle: LineStyle.Dashed,
      })
    }
    addLine(levels.resistance, 'Resistance', '#0f766e')
    addLine(levels.support, 'Support', '#c2410c')
    addLine(levels.entry, 'Entry', '#16a34a')
    addLine(levels.stop, 'Stop', '#dc2626')
    addLine(levels.target, 'Target', '#0369a1')

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
    return <p className="field-hint">No candles for this range.</p>
  }

  return (
    <div className="setup-chart" role="img" aria-label="Interactive price and volume chart">
      <div className="setup-chart-host" ref={hostRef} />
    </div>
  )
}
