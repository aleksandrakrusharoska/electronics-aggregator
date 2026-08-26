import heroBg from '../assets/hero-bg.png'
import logo from '../assets/logo.png'

const ACCENTS = [
  { text: 'text-cyan-400', border: 'hover:border-cyan-400/40', shadow: 'hover:shadow-cyan-500/20' },
  { text: 'text-orange-300', border: 'hover:border-orange-400/40', shadow: 'hover:shadow-orange-500/20' },
  { text: 'text-violet-300', border: 'hover:border-violet-400/40', shadow: 'hover:shadow-violet-500/20' },
]

export default function LandingPage({ stats, categories = [], onEnter, onAnalytics, onCategoryClick }) {
  const topCategories = categories.slice(0, 3)

  return (
    <div className="min-h-screen bg-[#0c1324] text-white">
      {/* Hero */}
      <section className="relative min-h-[85vh] flex items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${heroBg})` }} />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0c1324] via-[#0c1324]/80 to-[#0c1324]/30" />
        <div className="absolute inset-0 bg-gradient-to-r from-violet-500/20 via-transparent to-cyan-500/20 mix-blend-overlay" />

        <div className="relative z-10 flex flex-col items-center text-center px-6 max-w-3xl mx-auto py-24">
          <img src={logo} alt="ElectroFlow" className="h-16 w-16 rounded-2xl mb-6 shadow-[0_0_40px_rgba(139,92,246,0.4)]" />

          {stats && (
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 backdrop-blur-md border border-white/10 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-[11px] font-mono tracking-widest uppercase text-slate-300">
                {stats.total.toLocaleString()} огласи во живо
              </span>
            </div>
          )}

          <h1 className="text-5xl sm:text-6xl font-bold tracking-tight mb-4 drop-shadow-[0_0_30px_rgba(139,92,246,0.25)]">
            Електроника, <br className="hidden sm:block" />
            <span className="text-violet-300">споредена паметно.</span>
          </h1>

          <p className="text-slate-300 max-w-xl mb-8 text-lg">
            Ги собираме огласите за електроника од повеќе македонски портали на едно место, за полесно споредување на цени.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={onEnter}
              className="px-8 py-3 rounded-xl bg-violet-500 text-white font-medium hover:bg-violet-400 transition-colors shadow-[0_0_20px_rgba(139,92,246,0.4)] flex items-center justify-center gap-2 group"
            >
              Разгледај огласи
              <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </button>
            <button
              onClick={onAnalytics}
              className="px-8 py-3 rounded-full bg-white/5 backdrop-blur-xl border border-white/10 text-slate-100 font-medium hover:bg-white/10 hover:border-cyan-400/40 transition-colors"
            >
              Аналитика
            </button>
          </div>
        </div>

        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-50 z-10">
          <span className="text-[10px] tracking-widest uppercase text-slate-400 font-mono">Скролувај</span>
          <div className="w-px h-10 bg-gradient-to-b from-violet-400 to-transparent" />
        </div>
      </section>

      {/* Bento categories */}
      {topCategories.length > 0 && (
        <section className="py-16 px-6 max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <svg className="w-5 h-5 text-violet-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              Категории
            </h2>
            <button onClick={onEnter} className="text-xs font-mono uppercase tracking-widest text-violet-300 hover:text-violet-200 flex items-center gap-1">
              Сите огласи
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {topCategories.map((c, i) => {
              const accent = ACCENTS[i % ACCENTS.length]
              return (
                <button
                  key={c.name}
                  onClick={() => onCategoryClick(c.name)}
                  className={`group text-left rounded-2xl p-6 bg-[#0b0f19] border border-white/5 ${accent.border} hover:shadow-[0_0_40px_-10px] ${accent.shadow} transition-all`}
                >
                  <span className={`text-[10px] font-mono uppercase tracking-widest ${accent.text}`}>SYS.0{i + 1}</span>
                  <h3 className="mt-3 text-xl font-semibold text-white">{c.name}</h3>
                  <p className="mt-1 text-sm text-slate-500 font-mono">{c.count.toLocaleString()} огласи</p>
                </button>
              )
            })}
          </div>
        </section>
      )}

      <footer className="border-t border-white/5 py-8 px-6 text-center">
        <p className="text-xs text-slate-500 font-mono uppercase tracking-widest">ElectroFlow &middot; Дипломска работа</p>
      </footer>
    </div>
  )
}
