export default function Footer({ categories = [], onCategoryClick, onNavigate }) {
  const topCategories = categories.slice(0, 6)

  return (
    <footer className="mt-8 border-t border-slate-200 dark:border-slate-800 px-6 py-8">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-start sm:justify-between gap-8">
        {/* Brand */}
        <div className="max-w-xs">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-sm">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
              </svg>
            </div>
            <div className="font-semibold text-sm tracking-tight text-slate-900 dark:text-slate-100">
              Техника <span className="text-slate-400 dark:text-slate-500 font-normal">· агрегатор</span>
            </div>
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

      <div className="max-w-7xl mx-auto mt-6 pt-4 border-t border-slate-100 dark:border-slate-800/60">
        <p className="text-[11px] text-slate-400 dark:text-slate-600">
          Не сме поврзани со Pazar3.mk, Reklama5.mk или кој било друг наведен извор — сите огласи водат до оригиналната страница на изворот.
        </p>
      </div>
    </footer>
  )
}
