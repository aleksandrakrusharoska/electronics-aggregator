// The six condition categories the LLM parser normalizes every ad into,
// with their Macedonian labels (full, and short where space is tight).
export const CONDITIONS = {
  'New':             { label: 'Нов',              short: 'Нов' },
  'Used - Like New': { label: 'Како нов',         short: 'Како нов' },
  'Used - Good':     { label: 'Добра состојба',   short: 'Добра' },
  'Used - Fair':     { label: 'Солидна состојба', short: 'Солидна' },
  'Used':            { label: 'Користен',         short: 'Користен' },
  'For parts':       { label: 'За делови',        short: 'За делови' },
}

export const conditionLabel = c => CONDITIONS[c]?.label ?? c

// Same colours as the source dots in the sidebar
export const SOURCE_DOT = { reklama5: 'bg-blue-400', pazar3: 'bg-orange-400' }
