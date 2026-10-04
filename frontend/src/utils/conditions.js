// The six condition categories the LLM parser normalizes every ad into,
// with their labels and a colour that carries meaning: green tones are a
// positive signal, amber a warning, the middle of the scale stays neutral.
export const CONDITIONS = {
  'New':             { label: 'Нов',              short: 'Нов',      tone: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' },
  'Used - Like New': { label: 'Како нов',         short: 'Како нов', tone: 'bg-teal-50 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300' },
  'Used - Good':     { label: 'Добра состојба',   short: 'Добра',    tone: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
  'Used - Fair':     { label: 'Солидна состојба', short: 'Солидна',  tone: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
  'Used':            { label: 'Користен',         short: 'Користен', tone: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
  'For parts':       { label: 'За делови',        short: 'За делови', tone: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
}

export const conditionLabel = c => CONDITIONS[c]?.label ?? c

// Same colours as the source dots in the sidebar
export const SOURCE_DOT = { reklama5: 'bg-blue-400', pazar3: 'bg-orange-400' }
