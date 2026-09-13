import React, { useEffect, useMemo, useRef } from 'react'
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  UTCTimestamp,
  createChart,
  type IChartApi,
  type ISeriesApi,
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
  trendline?: string | number | null
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

/** Skip a level when it is essentially the same price as another already drawn. */
function near(a: number, b: number, rel = 0.0015): boolean {
  const scale = Math.max(Math.abs(a), Math.abs(b), 1)
  return Math.abs(a - b) / scale < rel
}

const DEFAULT_VISIBLE_BARS = 90

export function SetupChart({
  candles,
  levels,
  height = 360,
  variant = 'default',
}: {
  candles: ChartCandle[]
  levels: Levels
  height?: number
  /** Inspect: plan levels only. Evidence: structure + plan + markers. Structure: S/R + trendline. */
  variant?: 'default' | 'inspect' | 'evidence' | 'structure'
}) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const fittedKeyRef = useRef<string>('')
  const candlesRef = useRef(candles)
  const levelsRef = useRef(levels)
  candlesRef.current = candles
  levelsRef.current = levels
  const isInspect = variant === 'inspect'
  const isEvidence = variant === 'evidence'
  const isStructure = variant === 'structure'
  const roomy = isInspect || isEvidence || isStructure

  // Stable fingerprints — parent often recreates candles/levels arrays each render.
  const candlesKey = useMemo(
    () =>
      candles
        .map(
          (c) =>
            `${c.timestamp}:${c.open}:${c.high}:${c.low}:${c.close}:${c.volume ?? ''}`,
        )
        .join('|'),
    [candles],
  )
  const levelsKey = useMemo(() => JSON.stringify(levels ?? {}), [levels])

  useEffect(() => {
    if (!hostRef.current || candlesRef.current.length === 0) return
    const host = hostRef.current
    const candles = candlesRef.current
    const levels = levelsRef.current

    if (!chartRef.current) {
      const chart = createChart(host, {
        width: host.clientWidth || 860,
        height,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: '#64748b',
          fontSize: roomy ? 11 : 12,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: 'rgba(148, 163, 184, 0.12)' },
          horzLines: { color: 'rgba(148, 163, 184, 0.12)' },
        },
        rightPriceScale: {
          borderColor: 'rgba(148, 163, 184, 0.28)',
          minimumWidth: roomy ? 78 : 64,
          scaleMargins: roomy ? { top: 0.08, bottom: 0.18 } : { top: 0.1, bottom: 0.2 },
        },
        leftPriceScale: { visible: false },
        timeScale: {
          borderColor: 'rgba(148, 163, 184, 0.28)',
          timeVisible: true,
          rightOffset: roomy ? 6 : 4,
          barSpacing: roomy ? 8 : 7,
          // Allow user zoom/pan; do not pin edges (that fights manual zoom).
          fixLeftEdge: false,
          fixRightEdge: false,
        },
        crosshair: { mode: CrosshairMode.Normal },
        handleScroll: { vertTouchDrag: false },
        handleScale: {
          axisPressedMouseMove: true,
          mouseWheel: true,
          pinch: true,
        },
      })
      const candleSeries = chart.addCandlestickSeries({
        upColor: '#16a34a',
        downColor: '#dc2626',
        borderUpColor: '#16a34a',
        borderDownColor: '#dc2626',
        wickUpColor: '#16a34a',
        wickDownColor: '#dc2626',
        priceLineVisible: false,
        lastValueVisible: true,
      })
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
        color: 'rgba(71, 85, 105, 0.45)',
      })
      chart.priceScale('vol').applyOptions({
        scaleMargins: { top: roomy ? 0.78 : 0.72, bottom: 0 },
        borderVisible: false,
      })
      chartRef.current = chart
      candleSeriesRef.current = candleSeries
      volumeSeriesRef.current = volumeSeries

      const syncSize = () => {
        if (!hostRef.current || !chartRef.current) return
        chartRef.current.applyOptions({
          width: hostRef.current.clientWidth || 860,
          height,
        })
      }
      const observer = new ResizeObserver(syncSize)
      observer.observe(host)
      syncSize()
      ;(host as HTMLDivElement & { __tpRo?: ResizeObserver }).__tpRo = observer
    }

    const chart = chartRef.current
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    if (!chart || !candleSeries || !volumeSeries) return

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

    const preserved = chart.timeScale().getVisibleLogicalRange()
    candleSeries.setData(priceData)
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

    const toTime = (timestamp: string) => Math.floor(new Date(timestamp).getTime() / 1000) as UTCTimestamp
    const markers: Array<{
      time: UTCTimestamp
      position: 'aboveBar' | 'belowBar'
      color: string
      shape: 'circle' | 'arrowUp' | 'arrowDown' | 'square'
      text: string
    }> = []
    if (
      typeof levels.breakoutIndex === 'number' &&
      levels.breakoutIndex >= 0 &&
      levels.breakoutIndex < candles.length
    ) {
      markers.push({
        time: toTime(candles[levels.breakoutIndex].timestamp),
        position: 'aboveBar',
        color: '#7c3aed',
        shape: 'circle',
        text: 'B',
      })
    }
    if (
      typeof levels.retestIndex === 'number' &&
      levels.retestIndex >= 0 &&
      levels.retestIndex < candles.length
    ) {
      markers.push({
        time: toTime(candles[levels.retestIndex].timestamp),
        position: 'belowBar',
        color: '#f59e0b',
        shape: 'circle',
        text: 'R',
      })
    }
    if (
      typeof levels.confirmationIndex === 'number' &&
      levels.confirmationIndex >= 0 &&
      levels.confirmationIndex < candles.length
    ) {
      markers.push({
        time: toTime(candles[levels.confirmationIndex].timestamp),
        position: 'aboveBar',
        color: '#0ea5e9',
        shape: 'circle',
        text: 'C',
      })
    }
    candleSeries.setMarkers(markers)

    // Price lines: recreate series options by removing chart is heavy; clear via new candlestick
    // isn't available — use applyOptions trick: remove and re-add price lines by creating fresh ones.
    // lightweight-charts has no removeAllPriceLines; recreate candle series data already set.
    // Store line refs on series via createPriceLine only once per levelsKey by resetting series.
    // Simplest reliable approach: remove chart price lines by recreating candlestick series when levels change.
    // To avoid full chart destroy, we createPriceLine each update — old lines accumulate.
    // So on levelsKey change, remove candle series and re-add.
    // Actually IChartApi has no removeSeries that clears price lines easily in older API —
    // chart.removeSeries(candleSeries) then re-add.

    // Rebuild candle series when levels change to drop stale price lines.
    // Keep time scale range.
    chart.removeSeries(candleSeries)
    const nextCandle = chart.addCandlestickSeries({
      upColor: '#16a34a',
      downColor: '#dc2626',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
      priceLineVisible: false,
      lastValueVisible: true,
    })
    nextCandle.setData(priceData)
    nextCandle.setMarkers(markers)
    candleSeriesRef.current = nextCandle

    const drawn: number[] = []
    const addLine = (
      price: string | number | null | undefined,
      title: string,
      color: string,
      opts?: { axisLabel?: boolean; style?: LineStyle },
    ) => {
      const p = num(price)
      if (p == null) return
      if (drawn.some((existing) => near(existing, p))) return
      drawn.push(p)
      nextCandle.createPriceLine({
        price: p,
        title,
        color,
        lineWidth: roomy ? 2 : 1,
        axisLabelVisible: opts?.axisLabel ?? true,
        lineStyle: opts?.style ?? LineStyle.Dashed,
      })
    }

    if (isInspect) {
      addLine(levels.entry, 'Entry', '#16a34a', { style: LineStyle.Solid })
      addLine(levels.stop, 'Stop', '#dc2626')
      addLine(levels.target, 'Target', '#0369a1')
    } else if (isStructure) {
      addLine(levels.support, 'Support', '#c2410c')
      addLine(levels.resistance, 'Resistance', '#0f766e', { style: LineStyle.Solid })
      addLine(levels.trendline, 'Trendline', '#64748b', { style: LineStyle.Solid })
    } else if (isEvidence) {
      addLine(levels.resistance, 'Ceiling', '#0f766e')
      addLine(levels.support, 'Support', '#c2410c', { style: LineStyle.Solid })
      addLine(levels.entry, 'Entry', '#16a34a', { style: LineStyle.Solid })
      addLine(levels.stop, 'Stop', '#dc2626')
      addLine(levels.target, 'Target', '#0369a1')
    } else {
      addLine(levels.resistance, 'Ceiling', '#0f766e')
      addLine(levels.support, 'Floor', '#c2410c')
      addLine(levels.entry, 'Entry', '#16a34a')
      addLine(levels.stop, 'Stop', '#dc2626')
      addLine(levels.target, 'Target', '#0369a1')
    }

    const fitKey = `${candlesKey}::${variant}`
    if (fittedKeyRef.current !== fitKey) {
      const n = priceData.length
      if (n > DEFAULT_VISIBLE_BARS) {
        chart.timeScale().setVisibleLogicalRange({
          from: n - DEFAULT_VISIBLE_BARS,
          to: n + (roomy ? 2 : 1),
        })
      } else {
        chart.timeScale().fitContent()
      }
      fittedKeyRef.current = fitKey
    } else if (preserved) {
      chart.timeScale().setVisibleLogicalRange(preserved)
    }

    return () => {
      // Keep chart alive across data updates; only tear down on unmount via separate effect.
    }
  }, [candlesKey, levelsKey, height, isInspect, isEvidence, isStructure, roomy, variant])
  // candles/levels read from latest render when keys change — do not depend on object identity.

  useEffect(() => {
    return () => {
      const host = hostRef.current as (HTMLDivElement & { __tpRo?: ResizeObserver }) | null
      host?.__tpRo?.disconnect()
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
        candleSeriesRef.current = null
        volumeSeriesRef.current = null
        fittedKeyRef.current = ''
      }
    }
  }, [])

  if (candles.length === 0) {
    return (
      <div
        className={`setup-chart${roomy ? ' is-inspect' : ''} is-empty`}
        style={{ ['--setup-chart-height' as string]: `${height}px` }}
      >
        <p className="field-hint setup-chart-empty">No candles for this range.</p>
      </div>
    )
  }

  return (
    <div
      className={`setup-chart${roomy ? ' is-inspect' : ''}`}
      role="img"
      aria-label="Interactive price and volume chart"
      style={{ ['--setup-chart-height' as string]: `${height}px` }}
    >
      <div className="setup-chart-host" ref={hostRef} />
    </div>
  )
}
