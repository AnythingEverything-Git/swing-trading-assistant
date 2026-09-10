import { useState } from 'react'
import { HOME_GLOSSARY, type GlossaryTerm } from '../coach/glossary'

type Props = {
  onOpenSwing: () => void
  onOpenIntraday: () => void
  onOpenResearch: () => void
  onOpenBrief?: () => void
  onOpenCompare?: () => void
  guidedMode?: boolean
  dataLive?: boolean
  lastCandleTime?: string | null
}

export function HomeHub({
  onOpenSwing,
  onOpenIntraday,
  onOpenResearch,
  onOpenBrief,
  onOpenCompare,
  guidedMode = true,
  dataLive,
  lastCandleTime,
}: Props) {
  const [activeTip, setActiveTip] = useState<GlossaryTerm | null>(HOME_GLOSSARY[2] ?? null)

  return (
    <section className="panel home-hub wireframe-home" aria-label="Home hub">
      <div className="home-hub-hero">
        <p className="home-hub-brand">TradePilot</p>
        <h1 className="home-hub-headline">Your trading desks</h1>
        <p className="home-hub-lede">
          Pick a desk to find swing setups, run the morning board, or research any NSE name.
        </p>
      </div>

      {guidedMode ? (
        <div className="home-coach-row" aria-label="Beginner coach">
          <div className="home-coach-prompts">
            {HOME_GLOSSARY.slice(0, 3).map((term) => (
              <button
                key={term.id}
                type="button"
                className={`home-coach-chip${activeTip?.id === term.id ? ' active' : ''}`}
                onClick={() => setActiveTip(term)}
              >
                {term.prompt}
              </button>
            ))}
          </div>
          {activeTip ? (
            <aside className="home-coach-tip" role="note">
              <strong>{activeTip.title}</strong>
              <p>{activeTip.definition}</p>
            </aside>
          ) : null}
        </div>
      ) : null}

      <div className="home-hub-grid home-hub-grid-3">
        <article className="home-hub-card">
          <span className="home-hub-icon home-hub-icon-swing" aria-hidden="true" />
          <h2>Swing Desk</h2>
          <p>Swing trade setups on daily &amp; 4H charts.</p>
          <button type="button" className="primary-button home-hub-start" onClick={onOpenSwing}>
            Start
          </button>
        </article>

        <article className="home-hub-card">
          <span className="home-hub-icon home-hub-icon-intraday" aria-hidden="true" />
          <h2>Intraday Desk</h2>
          <p>Intraday setups on 5m &amp; 15m charts.</p>
          <button type="button" className="primary-button home-hub-start" onClick={onOpenIntraday}>
            Start
          </button>
        </article>

        <article className="home-hub-card">
          <span className="home-hub-icon home-hub-icon-research" aria-hidden="true" />
          <h2>Research FA+TA</h2>
          <p>Fundamental &amp; technical research in one place.</p>
          <div className="home-hub-card-actions">
            <button type="button" className="primary-button home-hub-start" onClick={onOpenResearch}>
              Start
            </button>
            {onOpenCompare ? (
              <button type="button" className="secondary-button home-hub-start" onClick={onOpenCompare}>
                Compare
              </button>
            ) : null}
          </div>
        </article>
      </div>

      {onOpenBrief ? (
        <div className="home-brief-cta">
          <button type="button" className="secondary-button" onClick={onOpenBrief}>
            Open Brief center
          </button>
        </div>
      ) : null}

      <footer className="home-hub-footer">
        <div className="home-hub-data">
          <span className="home-hub-footer-icon home-hub-footer-icon-data" aria-hidden="true" />
          <span className="home-hub-footer-label">Data</span>
          <span className={`data-pill ${dataLive ? 'live' : 'demo'}`}>
            <span className="data-pill-dot" aria-hidden="true" />
            {dataLive ? 'live' : 'demo'}
          </span>
        </div>
        <div className="home-hub-candle">
          <span className="home-hub-footer-icon home-hub-footer-icon-clock" aria-hidden="true" />
          <span className="home-hub-footer-label">Last candle time:</span>
          <span className="home-hub-candle-box">{lastCandleTime || '—:—'}</span>
        </div>
      </footer>
      <p className="home-hub-disclaimer">
        Educational tool. Past performance is not indicative of future results.
      </p>
    </section>
  )
}
