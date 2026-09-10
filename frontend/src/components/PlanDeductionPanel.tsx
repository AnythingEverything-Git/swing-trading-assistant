import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { DeductionStep } from '../planDeduction'

type Props = {
  symbol: string
  steps: DeductionStep[]
  baseUrl: string
  onClose: () => void
  /** @deprecated Modal always shows full steps; kept for call-site compatibility. */
  compact?: boolean
}

type RephraseState = {
  steps: DeductionStep[]
  provider: 'gemini' | 'template' | 'loading'
  detail?: string | null
}

/** UC-E4 / Inspect — Strategy Steps modal (engine facts; AI may polish wording only). */
export function PlanDeductionPanel({ symbol, steps, baseUrl, onClose }: Props) {
  const [view, setView] = useState<RephraseState>({ steps, provider: 'loading' })

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setView({ steps, provider: 'loading' })

    void (async () => {
      try {
        const response = await fetch(`${baseUrl}/api/v1/research/plan-deduction/rephrase`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol,
            steps: steps.map((step) => ({
              id: step.id,
              title: step.title,
              value: step.value,
              summary: step.summary,
              details: step.details,
            })),
          }),
        })
        if (!response.ok) {
          if (!cancelled) setView({ steps, provider: 'template', detail: 'rephrase_http_error' })
          return
        }
        const payload = (await response.json()) as {
          steps?: DeductionStep[]
          provider?: string
          detail?: string | null
        }
        if (cancelled) return
        const next = Array.isArray(payload.steps) && payload.steps.length === steps.length ? payload.steps : steps
        const locked = next.map((step, index) => ({
          id: steps[index].id,
          title: steps[index].title,
          value: steps[index].value,
          summary: step.summary || steps[index].summary,
          details:
            Array.isArray(step.details) && step.details.length > 0 ? step.details : steps[index].details,
        }))
        setView({
          steps: locked,
          provider: payload.provider === 'gemini' ? 'gemini' : 'template',
          detail: payload.detail,
        })
      } catch {
        if (!cancelled) setView({ steps, provider: 'template', detail: 'rephrase_unavailable' })
      }
    })()

    return () => {
      cancelled = true
    }
  }, [baseUrl, steps, symbol])

  return createPortal(
    <div
      className="strategy-steps-overlay"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="strategy-steps-modal plan-deduction"
        role="dialog"
        aria-modal="true"
        aria-labelledby="strategy-steps-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="plan-deduction-head">
          <div>
            <h4 id="strategy-steps-title">Strategy Steps · {symbol}</h4>
            <p>
              Numbers and conclusions come only from strategy rules. AI may polish wording — it cannot change
              levels, risk math, or the trade plan.
            </p>
            <p className="field-hint plan-deduction-provider">
              {view.provider === 'loading'
                ? 'Polishing wording…'
                : view.provider === 'gemini'
                  ? 'Wording polished by AI · facts locked to strategy rules'
                  : 'Showing strategy wording (AI polish unavailable or unchanged)'}
            </p>
          </div>
          <button type="button" className="ghost-btn capital-risk-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <ol className="plan-deduction-steps">
          {view.steps.map((step) => (
            <li key={step.id} className="plan-deduction-step">
              <div className="plan-deduction-step-top">
                <strong>{step.title}</strong>
                <span className="plan-deduction-value">{step.value}</span>
              </div>
              <p className="plan-deduction-summary">{step.summary}</p>
              <ul>
                {step.details.map((line, detailIndex) => (
                  <li key={`${step.id}-${detailIndex}`}>{line}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </div>
    </div>,
    document.body,
  )
}
