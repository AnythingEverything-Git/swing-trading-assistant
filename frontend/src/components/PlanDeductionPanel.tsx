import React, { useEffect, useState } from 'react'
import type { DeductionStep } from '../planDeduction'

type Props = {
  symbol: string
  steps: DeductionStep[]
  baseUrl: string
  onClose?: () => void
  /** Wireframe-style tile: shorter intro, denser steps. */
  compact?: boolean
}

type RephraseState = {
  steps: DeductionStep[]
  provider: 'gemini' | 'template' | 'loading'
  detail?: string | null
}

export function PlanDeductionPanel({ symbol, steps, baseUrl, onClose, compact = false }: Props) {
  const [view, setView] = useState<RephraseState>({ steps, provider: 'loading' })

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
        // Lock titles/values to the rules-built source even if the API echoed them.
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

  return (
    <div
      className={`plan-deduction${compact ? ' is-compact' : ''}`}
      role="region"
      aria-label={`How decided ${symbol}`}
    >
      {!compact ? (
        <div className="plan-deduction-head">
          <div>
            <h4>How decided · {symbol}</h4>
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
          {onClose ? (
            <button type="button" className="ghost-btn" onClick={onClose} aria-label="Close">
              ×
            </button>
          ) : null}
        </div>
      ) : (
        <p className="plan-deduction-compact-meta" aria-live="polite">
          {view.provider === 'loading'
            ? 'Polishing wording…'
            : view.provider === 'gemini'
              ? 'Facts locked · wording polished'
              : 'Facts locked to strategy rules'}
        </p>
      )}
      <ol className="plan-deduction-steps">
        {view.steps.map((step, index) => (
          <li key={step.id} className="plan-deduction-step">
            <div className="plan-deduction-step-top">
              <strong>
                {compact ? (
                  <>
                    <span className="plan-deduction-index">{index + 1}</span>
                    {step.title.replace(/^\d+\.\s*/, '')}
                  </>
                ) : (
                  step.title
                )}
              </strong>
              <span className="plan-deduction-value">{step.value}</span>
            </div>
            {compact ? (
              <p className="plan-deduction-summary">{step.summary}</p>
            ) : (
              <>
                <p className="plan-deduction-summary">{step.summary}</p>
                <ul>
                  {step.details.map((line, detailIndex) => (
                    <li key={`${step.id}-${detailIndex}`}>{line}</li>
                  ))}
                </ul>
              </>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}
