import { buildInvalidationView, type InvalidationFacts } from '../coach/invalidation'

type Props = {
  facts: InvalidationFacts | null
  className?: string
}

/** UC-F2 — structured invalidation panel (not chat). */
export function InvalidationPanel({ facts, className = '' }: Props) {
  if (!facts || (!facts.invalidation && !facts.reason_code && !facts.detail)) {
    return (
      <aside className={`invalidation-panel is-empty ${className}`.trim()} aria-label="Invalidation">
        <h3>
          <span className="coach-ico coach-ico-alert" aria-hidden="true" />
          Invalidation
        </h3>
        <p className="field-hint">Select a setup to see plain-English block reasons and checklist.</p>
      </aside>
    )
  }

  const view = buildInvalidationView(facts)

  return (
    <aside className={`invalidation-panel ${className}`.trim()} aria-label="Invalidation">
      <h3>
        <span className="coach-ico coach-ico-alert" aria-hidden="true" />
        {view.title}
      </h3>
      <dl className="invalidation-facts">
        <div>
          <dt>Symbol</dt>
          <dd>{view.symbol}</dd>
        </div>
        {view.reasonCode ? (
          <div>
            <dt>Reason</dt>
            <dd>
              <code>{view.reasonCode}</code>
            </dd>
          </div>
        ) : null}
      </dl>
      <p className="invalidation-plain">
        <strong>Plain English:</strong> {view.plainEnglish}
      </p>
      <div className="invalidation-checklist">
        <strong>Invalidation checklist</strong>
        <ul>
          {view.checklist.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
      <p className="invalidation-config">
        <span className="coach-ico coach-ico-shield" aria-hidden="true" />
        {view.configNote}
      </p>
    </aside>
  )
}
