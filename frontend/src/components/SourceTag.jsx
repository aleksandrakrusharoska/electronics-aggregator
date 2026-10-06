import { inferSource, sourceLabel } from '../utils/inferSource'
import { SOURCE_DOT } from '../utils/conditions'

// The portal(s) an ad is on, each with its coloured dot: "• Пазар3" or, for
// the same seller's listing on both portals (also_on, from the duplicate
// groups), "• Пазар3 • Реклама5".
export default function SourceTag({ ad }) {
  const main = inferSource(ad)
  const sources = [main, ...(ad.also_on || []).map(o => inferSource(o))]
    .filter((s, i, all) => s && all.indexOf(s) === i)
  if (!sources.length) return null
  return (
    <span
      className="flex items-center gap-2 font-medium text-slate-500 dark:text-slate-400"
      title={sources.length > 1 ? 'Огласено на двата портали' : undefined}
    >
      {sources.map(s => (
        <span key={s} className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${SOURCE_DOT[s] || 'bg-slate-400'}`} />
          {sourceLabel(s)}
        </span>
      ))}
    </span>
  )
}
