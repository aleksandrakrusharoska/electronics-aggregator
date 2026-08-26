const ACCENTS = [
  { text: 'text-cyan-400', border: 'hover:border-cyan-400/40', shadow: 'hover:shadow-cyan-500/20' },
  { text: 'text-orange-300', border: 'hover:border-orange-400/40', shadow: 'hover:shadow-orange-500/20' },
  { text: 'text-violet-300', border: 'hover:border-violet-400/40', shadow: 'hover:shadow-violet-500/20' },
]

export default function Hero({ stats, categories = [], onBrowse, onAnalytics, onCategoryClick }) {
  const topCategories = categories.slice(0, 3)

  return (
    <section className="relative overflow-hidden rounded-2xl mx-6 mt-6 bg-[#0b0f19] border border-white/5">
      <div className="absolute inset-0 bg-gradient-to-br from-violet-500/10 via-transparent to-cyan-500/10 pointer-events-none" />

      <div className="relative px-6 py-16 sm:py-20 flex flex-col items-center text-center">
        {stats && (
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-[11px] font-mono tracking-widest uppercase text-slate-400">
              {stats.total.toLocaleString()} огласи во живо
            </span>
          </div>
        )}

        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white mb-4 max-w-2xl">
          Електроника, <span className="text-violet-300">споредена паметно.</span>
        </h1>

        <p className="text-slate-400 max-w-xl mb-8">
          Ги собираме огласите за електроника од повеќе македонски портали на едно место, за полесно споредување на цени.
        </p>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={onBrowse}
            className="px-6 py-2.5 rounded-xl bg-violet-500 text-white font-medium hover:bg-violet-400 transition-colors shadow-[0_0_20px_rgba(139,92,246,0.4)]"
          >
            Разгледај огласи
          </button>
          <button
            onClick={onAnalytics}
            className="px-6 py-2.5 rounded-full bg-white/5 border border-white/10 text-slate-200 font-medium hover:bg-white/10 hover:border-cyan-400/40 transition-colors"
          >
            Аналитика
          </button>
        </div>
      </div>

      {topCategories.length > 0 && (
        <div className="relative grid grid-cols-1 sm:grid-cols-3 gap-px bg-white/5 border-t border-white/5">
          {topCategories.map((c, i) => {
            const accent = ACCENTS[i % ACCENTS.length]
            return (
              <button
                key={c.name}
                onClick={() => onCategoryClick(c.name)}
                className={`group text-left p-6 bg-[#0b0f19] border border-transparent ${accent.border} hover:shadow-[0_0_30px_-8px] ${accent.shadow} transition-all`}
              >
                <span className={`text-[10px] font-mono uppercase tracking-widest ${accent.text}`}>
                  SYS.0{i + 1}
                </span>
                <h3 className="mt-2 text-lg font-semibold text-white">{c.name}</h3>
                <p className="mt-1 text-xs text-slate-500 font-mono">{c.count.toLocaleString()} огласи</p>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
