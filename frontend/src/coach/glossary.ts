/** Beginner glossary — static coach copy, not LLM. */

export type GlossaryTerm = {
  id: string
  prompt: string
  title: string
  definition: string
}

export const HOME_GLOSSARY: GlossaryTerm[] = [
  {
    id: 'rvol',
    prompt: 'What does RVOL mean?',
    title: 'RVOL',
    definition:
      'Relative volume — how busy trading is versus a typical day. Higher RVOL means more participation behind a move.',
  },
  {
    id: 'no-profit-goal',
    prompt: 'Why no profit goal intraday?',
    title: 'Intraday exits',
    definition:
      'ORB V1 exits on the safety stop or forced flatten at 15:10. There is no separate profit-goal target for same-day practice.',
  },
  {
    id: 'safety-exit',
    prompt: 'What is a safety exit?',
    title: 'Safety exit',
    definition: 'A stop-loss that protects your money — the engine owns this level; Copilot never invents it.',
  },
  {
    id: 'entry-sl-target',
    prompt: 'Who owns Entry / SL / Target?',
    title: 'Engine levels',
    definition:
      'The strategy engine computes Entry, Stop, and Target from rules (CONFIG_V1). UI and briefs only repeat those numbers.',
  },
]

export function findGlossary(id: string): GlossaryTerm | undefined {
  return HOME_GLOSSARY.find((term) => term.id === id)
}
