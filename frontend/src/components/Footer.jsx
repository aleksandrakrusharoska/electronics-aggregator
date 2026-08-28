import logoMark from '../assets/logo-mark.svg'

export default function Footer({ categories = [], onCategoryClick, onNavigate }) {
  const topCategories = categories.slice(0, 6)

  return (
    <footer className="border-t border-slate-200 dark:border-slate-800 px-6 py-8">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row sm:items-start sm:justify-between gap-8">
        {/* Brand */}
        <div className="max-w-xs">
          <div className="flex items-center gap-2">
            <img src={logoMark} alt="" className="h-7 w-7" />
            <span className="text-lg font-extrabold tracking-tight">
              <span className="text-slate-900 dark:text-white">Electro</span>
              <span className="text-violet-600 dark:text-violet-400">Flow</span>
            </span>
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-2 leading-relaxed">
            Ги собираме огласите за електроника од повеќе македонски портали на едно место, за полесно споредување на цени.
          </p>
        </div>

        {/* Category quick links */}
        {topCategories.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2.5">
              Категории
            </h3>
            <ul className="space-y-1.5">
              {topCategories.map(c => (
                <li key={c.name}>
                  <button
                    onClick={() => onCategoryClick(c.name)}
                    className="text-xs text-slate-500 dark:text-slate-400 hover:text-violet-600 dark:hover:text-violet-400 transition-colors"
                  >
                    {c.name}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Pages */}
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2.5">
            Страници
          </h3>
          <ul className="space-y-1.5">
            <li>
              <button
                onClick={() => onNavigate('landing')}
                className="text-xs text-slate-500 dark:text-slate-400 hover:text-violet-600 dark:hover:text-violet-400 transition-colors"
              >
                Почетна
              </button>
            </li>
            <li>
              <button
                onClick={() => onNavigate('ads')}
                className="text-xs text-slate-500 dark:text-slate-400 hover:text-violet-600 dark:hover:text-violet-400 transition-colors"
              >
                Огласи
              </button>
            </li>
            <li>
              <button
                onClick={() => onNavigate('analytics')}
                className="text-xs text-slate-500 dark:text-slate-400 hover:text-violet-600 dark:hover:text-violet-400 transition-colors"
              >
                Аналитика
              </button>
            </li>
          </ul>
        </div>
      </div>

      <div className="max-w-5xl mx-auto mt-6 pt-4 border-t border-slate-100 dark:border-slate-800/60">
        <p className="text-[11px] text-slate-400 dark:text-slate-600">
          Не сме поврзани со Pazar3.mk, Reklama5.mk или кој било друг наведен извор — сите огласи водат до оригиналната страница на изворот.
        </p>
      </div>
    </footer>
  )
}
