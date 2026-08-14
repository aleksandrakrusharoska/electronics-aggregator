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
  { value: 'product', label: 'Производи' },
  { value: 'service', label: 'Услуги' },
  { value: 'wanted',  label: 'Барање' },
  { value: '',        label: 'Сите' },
]

const AD_TYPE_ICON_PATHS = {
  product: 'M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m16.5 0a48.108 48.108 0 00-3.478-.397m-12.022.397a48.108 48.108 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0M12 12.75h.008v.008H12v-.008z',
  service: 'M11.42 15.17L17.25 21A2.652 2.652 0 1021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z',
  wanted: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
}

function AdTypeIcon({ type }) {
  const d = AD_TYPE_ICON_PATHS[type]
  if (!d) return null
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  )
}

const CONDITIONS = [
  { value: '',               label: 'Сите' },
  { value: 'New',            label: 'Нов' },
  { value: 'Used - Like New', label: 'Како нов' },
  { value: 'Used',           label: 'Користен' },
  { value: 'For parts',      label: 'За делови' },
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
                  <AdTypeIcon type={t.value} />
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
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.169.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" />
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
        <div className="relative">
          <select
            className="input-base text-sm appearance-none pr-9"
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
          <svg
            className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
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
