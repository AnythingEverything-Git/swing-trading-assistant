import React from 'react'
import type { DeductionStep } from '../planDeduction'

type Props = {
  symbol: string
  steps: DeductionStep[]
  onClose?: () => void
}

export function PlanDeductionPanel({ symbol, steps, onClose }: Props) {
  return (
    <div className="plan-deduction" role="region" aria-label={`How TradePilot decided ${symbol}`}>
      <div className="plan-deduction-head">
        <div>
          <h4>How TradePilot decided {symbol}</h4>
          <p>
            Follow these steps in order. Every number comes from the strategy rules — nothing is guessed by
            AI.
          </p>
        </div>
        {onClose ? (
          <button type="button" className="ghost-btn" onClick={onClose}>
            Hide
          </button>
        ) : null}
      </div>
      <ol className="plan-deduction-steps">
        {steps.map((step) => (
          <li key={step.id} className="plan-deduction-step">
            <div className="plan-deduction-step-top">
              <strong>{step.title}</strong>
              <span className="plan-deduction-value">{step.value}</span>
            </div>
            <p className="plan-deduction-summary">{step.summary}</p>
            <ul>
              {step.details.map((line, index) => (
                <li key={`${step.id}-${index}`}>{line}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  )
}
