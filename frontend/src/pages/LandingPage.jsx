import heroBg from '../assets/hero-bg.png'
import logo from '../assets/logo-tile.svg'

export default function LandingPage({ onEnter, onAnalytics }) {

  return (
    <div className="min-h-screen flex flex-col bg-[#0c1324] text-white">
      {/* Hero */}
      <section className="relative flex-1 flex items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${heroBg})` }} />
        {/* light overall tint so the laptop shows; a soft dark spot behind the text keeps it readable */}
        <div className="absolute inset-0 bg-gradient-to-t from-[#0c1324] via-[#0c1324]/35 to-[#0c1324]/10" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_55%_40%_at_50%_55%,rgba(12,19,36,0.75),transparent)]" />
        <div className="absolute inset-0 bg-gradient-to-r from-violet-500/20 via-transparent to-cyan-500/20 mix-blend-overlay" />

        <div className="relative z-10 flex flex-col items-center text-center px-6 max-w-4xl mx-auto py-24">
          <img src={logo} alt="ElectroFlow" className="h-16 w-16 rounded-2xl mb-6 shadow-[0_0_40px_rgba(139,92,246,0.4)]" />

          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4 drop-shadow-[0_0_30px_rgba(139,92,246,0.25)]">
            Сета електроника <br className="hidden sm:block" />
            <span className="text-violet-300">на едно место</span>
          </h1>

          <p className="text-slate-300 mb-8 text-lg sm:whitespace-nowrap">
            Пребарувајте ги огласите од pazar3 и reklama5 и проверете дали цената е добра.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={onEnter}
              className="px-8 py-3 rounded-xl bg-violet-500 text-white font-medium hover:bg-violet-400 transition-colors shadow-[0_0_20px_rgba(139,92,246,0.4)] flex items-center justify-center gap-2 group"
            >
              Разгледајте огласи
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
      </section>

      <footer className="shrink-0 border-t border-white/5 py-5 px-6 text-center">
        <p className="text-xs text-slate-500 uppercase tracking-widest">ElectroFlow &middot; Дипломска работа</p>
      </footer>
    </div>
  )
}
