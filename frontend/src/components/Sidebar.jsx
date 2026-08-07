const SOURCES = [
  { id: 'reklama5', label: 'Reklama5' },
  { id: 'pazar3',   label: 'Pazar3' },
]

const SORTS = [
  { value: 'newest',     label: 'Најнови' },
  { value: 'price_asc',  label: 'Цена ↑' },
  { value: 'price_desc', label: 'Цена ↓' },
]

const AD_TYPES = [
  { value: 'product', label: 'Производи',  icon: '📦' },
  { value: 'service', label: 'Услуги',     icon: '🔧' },
  { value: 'wanted',  label: 'Барање',     icon: '🔍' },
  { value: '',        label: 'Сите',       icon: null },
]

const CONDITIONS = [
  { value: '',          label: 'Сите' },
  { value: 'new',       label: 'Нов' },
  { value: 'like_new',  label: 'Како нов' },
  { value: 'used',      label: 'Користен' },
  { value: 'for_parts', label: 'За делови' },
]

const PRICE_PRESETS = [
  { label: 'До 50 €',      min: '',   max: '50' },
  { label: '50–200 €',     min: '50', max: '200' },
  { label: '200–500 €',    min: '200',max: '500' },
  { label: '500–1000 €',   min: '500',max: '1000' },
  { label: '1000+ €',      min: '1000',max: '' },
]

function SectionHeader({ children }) {
  return (
    <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2.5">
      {children}
    </h3>
  )
}

export default function Sidebar({ filters, stats, categories, onChange, onClear }) {
  const hasFilters =
    filters.source || filters.category || filters.condition ||
    filters.min_price || filters.max_price || filters.q ||
    filters.good_deal_only || filters.ad_type !== 'product'

  const activePreset = PRICE_PRESETS.find(
    p => p.min === (filters.min_price || '') && p.max === (filters.max_price || '')
  )

  const setPreset = preset => {
    onChange('min_price', preset.min)
    onChange('max_price', preset.max)
  }

  return (
    <aside className="w-60 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 overflow-y-auto sticky top-14 h-[calc(100vh-3.5rem)] p-4 space-y-5">

      {/* Извори */}
      <section>
        <SectionHeader>Извори</SectionHeader>
        <div className="space-y-0.5">
          {SOURCES.map(src => {
            const count = stats?.sources?.[src.id] ?? null
            const active = filters.source === src.id
            return (
              <button
                key={src.id}
                onClick={() => onChange('source', active ? '' : src.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                  active
                    ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 font-medium'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${src.id === 'reklama5' ? 'bg-blue-400' : 'bg-orange-400'}`} />
                  {src.label}
                </span>
                {count !== null && (
                  <span className="text-xs font-mono text-slate-400 dark:text-slate-500">
                    {count.toLocaleString()}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </section>

      {/* Тип на оглас */}
      <section>
        <SectionHeader>Тип на оглас</SectionHeader>
        <div className="space-y-0.5">
          {AD_TYPES.map(t => {
            const count =
              t.value === 'service' ? stats?.ad_types?.service :
              t.value === 'wanted'  ? stats?.ad_types?.wanted  :
              t.value === ''        ? stats?.total : null
            const active = filters.ad_type === t.value
            return (
              <button
                key={t.value}
                onClick={() => onChange('ad_type', t.value)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                  active
                    ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 font-medium'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <span className="flex items-center gap-2">
                  {t.icon && <span className="text-base leading-none">{t.icon}</span>}
                  {t.label}
                </span>
                {count != null && (
                  <span className="text-xs font-mono text-slate-400 dark:text-slate-500">
                    {count.toLocaleString()}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </section>

      {/* Добри цени (спорeдено со нова цена) */}
      <section>
        <SectionHeader>Детекција</SectionHeader>
        <button
          onClick={() => onChange('good_deal_only', !filters.good_deal_only)}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
            filters.good_deal_only
              ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 font-medium'
              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
          </svg>
          Само добри цени
          {stats?.good_deals > 0 && (
            <span className="ml-auto text-xs font-mono text-slate-400 dark:text-slate-500">
              {stats.good_deals.toLocaleString()}
            </span>
          )}
        </button>
      </section>

      {/* Состојба */}
      <section>
        <SectionHeader>Состојба</SectionHeader>
        <div className="flex flex-wrap gap-1.5">
          {CONDITIONS.map(c => (
            <button
              key={c.value}
              onClick={() => onChange('condition', c.value)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                filters.condition === c.value
                  ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </section>

      {/* Категорија */}
      <section>
        <SectionHeader>Категорија</SectionHeader>
        <select
          className="input-base text-sm"
          value={filters.category}
          onChange={e => onChange('category', e.target.value)}
        >
          <option value="">Сите категории</option>
          {categories.map(c => (
            <option key={c.name} value={c.name}>
              {c.name} ({c.count.toLocaleString()})
            </option>
          ))}
        </select>
      </section>

      {/* Цена */}
      <section>
        <SectionHeader>Цена (EUR)</SectionHeader>
        {/* Presets */}
        <div className="flex flex-wrap gap-1 mb-2">
          {PRICE_PRESETS.map(p => (
            <button
              key={p.label}
              onClick={() => activePreset?.label === p.label ? (onChange('min_price', ''), onChange('max_price', '')) : setPreset(p)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                activePreset?.label === p.label
                  ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {/* Manual inputs */}
        <div className="flex gap-2">
          <input
            type="number"
            className="input-base text-sm"
            placeholder="Од"
            min={0}
            value={filters.min_price}
            onChange={e => onChange('min_price', e.target.value)}
          />
          <input
            type="number"
            className="input-base text-sm"
            placeholder="До"
            min={0}
            value={filters.max_price}
            onChange={e => onChange('max_price', e.target.value)}
          />
        </div>
      </section>

      {/* Сортирај */}
      <section>
        <SectionHeader>Сортирај</SectionHeader>
        <div className="flex flex-wrap gap-1.5">
          {SORTS.map(s => (
            <button
              key={s.value}
              onClick={() => onChange('sort', s.value)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                filters.sort === s.value
                  ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      {/* Исчисти */}
      {hasFilters && (
        <button
          onClick={onClear}
          className="w-full py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-sm text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          Исчисти филтри
        </button>
      )}
    </aside>
  )
}
