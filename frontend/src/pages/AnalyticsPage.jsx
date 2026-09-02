import { useState, useEffect } from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, Cell,
} from 'recharts'
import { fetchBrandStats, fetchDepreciation, fetchCategories, fetchGoodDeals, fetchTrend, fetchScrapeActivity } from '../api/client'
import { sourceLabel } from '../utils/inferSource'

const CONDITION_ORDER = ['New', 'Used - Like New', 'Used - Good', 'Used - Fair', 'Used', 'For parts']
const CONDITION_LABELS_MK = {
  'New': 'Нов',
  'Used - Like New': 'Како нов',
  'Used - Good': 'Добра состојба',
  'Used - Fair': 'Солидна состојба',
  'Used': 'Користен',
  'For parts': 'За делови',
}
const DEPRECIATION_COLORS = ['#10b981', '#34d399', '#7c3aed', '#f59e0b', '#f97316', '#ef4444']

function DepreciationTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 text-xs shadow-lg min-w-[160px]">
      <p className="font-semibold text-slate-900 dark:text-slate-100 mb-2">{d.label}</p>
      <div className="space-y-1">
        <Row label="Огласи" value={d.count.toLocaleString()} />
        <Row label="Просечно" value={`${d.avg_pct_of_new}% од нов`} color="text-violet-600 dark:text-violet-400" />
        <Row label="Медијана" value={`${d.median_pct_of_new}% од нов`} />
      </div>
    </div>
  )
}

function DepreciationChart({ theme }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'
  const cursorColor = isDark ? '#1e293b80' : '#f8fafc'

  useEffect(() => {
    fetchDepreciation()
      .then(d => {
        const byCondition = Object.fromEntries(d.map(r => [r.condition, r]))
        setData(
          CONDITION_ORDER
            .filter(c => byCondition[c])
            .map(c => ({ ...byCondition[c], label: CONDITION_LABELS_MK[c] || c }))
        )
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading || error || data.length === 0) return null

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Намалување на вредност по состојба</h2>
      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 mb-4">
        Просечна цена на употребени уреди како % од цената на нов уред за истиот модел (споредено со Setec.mk)
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: axisColor }}
            tickLine={false}
            axisLine={{ stroke: gridColor }}
            interval={0}
            angle={-20}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tick={{ fontSize: 11, fill: axisColor }}
            tickLine={{ stroke: gridColor }}
            axisLine={{ stroke: gridColor }}
            tickFormatter={v => `${v}%`}
          />
          <Tooltip content={<DepreciationTooltip />} cursor={{ fill: cursorColor }} />
          <Bar dataKey="avg_pct_of_new" radius={[4, 4, 0, 0]} maxBarSize={64}>
            {data.map((entry, i) => (
              <Cell key={entry.condition} fill={DEPRECIATION_COLORS[i % DEPRECIATION_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

const MONTH_SHORT_MK = ['јан', 'фев', 'мар', 'апр', 'мај', 'јун', 'јул', 'авг', 'сеп', 'окт', 'ное', 'дек']
const dayLabel = iso => {
  const [, m, d] = iso.split('-')
  return `${parseInt(d, 10)} ${MONTH_SHORT_MK[parseInt(m, 10) - 1]}`
}

function ScrapeActivityChart({ theme }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'
  const cursorColor = isDark ? '#1e293b80' : '#f8fafc'

  useEffect(() => {
    fetchScrapeActivity()
      .then(d => setData(d.map(r => ({ ...r, label: dayLabel(r.date), total: r.pazar3 + r.reklama5 }))))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading || error || data.length === 0) return null

  const today = data[data.length - 1]

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Скрапирани денес</h2>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            Нови огласи регистрирани денес по извор (последни 14 дена подолу) — вклучува и backfill-скокови, не само тековни огласи
          </p>
        </div>
        <div className="flex items-center gap-5 shrink-0">
          <div className="text-right">
            <div className="text-2xl font-bold font-mono text-violet-600 dark:text-violet-400">{today.total.toLocaleString()}</div>
            <div className="text-[11px] text-slate-400 dark:text-slate-500">вкупно</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-semibold font-mono text-orange-500">{today.pazar3.toLocaleString()}</div>
            <div className="text-[11px] text-slate-400 dark:text-slate-500">{sourceLabel('pazar3')}</div>
          </div>
          <div className="text-right">
            <div className="text-lg font-semibold font-mono text-sky-500">{today.reklama5.toLocaleString()}</div>
            <div className="text-[11px] text-slate-400 dark:text-slate-500">{sourceLabel('reklama5')}</div>
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: axisColor }} tickLine={false} axisLine={{ stroke: gridColor }} />
          <YAxis tick={{ fontSize: 11, fill: axisColor }} tickLine={{ stroke: gridColor }} axisLine={{ stroke: gridColor }} />
          <Tooltip
            cursor={{ fill: cursorColor }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              const d = payload[0].payload
              return (
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 text-xs shadow-lg min-w-[140px]">
                  <p className="font-semibold text-slate-900 dark:text-slate-100 mb-2">{label}</p>
                  <Row label={sourceLabel('pazar3')} value={d.pazar3.toLocaleString()} color="text-orange-500" />
                  <Row label={sourceLabel('reklama5')} value={d.reklama5.toLocaleString()} color="text-sky-500" />
                </div>
              )
            }}
          />
          <Bar dataKey="pazar3" stackId="s" fill="#f97316" radius={[0, 0, 0, 0]} maxBarSize={28} />
          <Bar dataKey="reklama5" stackId="s" fill="#0ea5e9" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function TrendChart({ theme }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'

  useEffect(() => {
    fetchTrend()
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading || error || data.length === 0) return null

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Активност на пазарот</h2>
      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 mb-4">
        Број на нови огласи по месец, последните 12 месеци
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: axisColor }} tickLine={false} axisLine={{ stroke: gridColor }} />
          <YAxis tick={{ fontSize: 11, fill: axisColor }} tickLine={{ stroke: gridColor }} axisLine={{ stroke: gridColor }} />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              return (
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 text-xs shadow-lg min-w-[140px]">
                  <p className="font-semibold text-slate-900 dark:text-slate-100 mb-2">{label}</p>
                  {payload.map(p => (
                    <Row
                      key={p.dataKey}
                      label={sourceLabel(p.dataKey)}
                      value={p.value.toLocaleString()}
                      color={p.dataKey === 'pazar3' ? 'text-orange-500' : 'text-sky-500'}
                    />
                  ))}
                </div>
              )
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={sourceLabel} />
          <Line type="monotone" dataKey="pazar3" stroke="#f97316" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="reklama5" stroke="#0ea5e9" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function CategoryChart({ theme }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'
  const cursorColor = isDark ? '#1e293b80' : '#f8fafc'

  useEffect(() => {
    fetchCategories()
      .then(d => setData(d.slice(0, 12)))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading || error || data.length === 0) return null

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Најчести категории</h2>
      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 mb-4">
        Број на огласи по категорија (топ 12)
      </p>
      <ResponsiveContainer width="100%" height={Math.max(data.length * 32 + 20, 100)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 32, top: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11, fill: axisColor }} tickLine={{ stroke: gridColor }} axisLine={{ stroke: gridColor }} />
          <YAxis dataKey="name" type="category" width={140} tick={{ fontSize: 11, fill: axisColor }} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ fill: cursorColor }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              return (
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-2 text-xs shadow-lg">
                  <span className="font-semibold text-slate-900 dark:text-slate-100">{payload[0].payload.name}</span>: {payload[0].value.toLocaleString()}
                </div>
              )
            }}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={20} fill="#7c3aed" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function GoodDealChart({ theme }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'
  const cursorColor = isDark ? '#1e293b80' : '#f8fafc'

  useEffect(() => {
    fetchGoodDeals()
      .then(d => setData(d.slice(0, 12)))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading || error || data.length === 0) return null

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Брендови со најмногу добри цени</h2>
      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 mb-4">
        % од огласите означени како добра цена, само брендови со 10+ огласи
      </p>
      <ResponsiveContainer width="100%" height={Math.max(data.length * 32 + 20, 100)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 32, top: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={v => `${v}%`}
            tick={{ fontSize: 11, fill: axisColor }}
            tickLine={{ stroke: gridColor }}
            axisLine={{ stroke: gridColor }}
          />
          <YAxis dataKey="brand" type="category" width={72} tick={{ fontSize: 12, fill: axisColor }} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ fill: cursorColor }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const d = payload[0].payload
              return (
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 text-xs shadow-lg min-w-[160px]">
                  <p className="font-semibold text-slate-900 dark:text-slate-100 mb-2">{d.brand}</p>
                  <Row label="Добри цени" value={`${d.good_deal_pct}%`} color="text-emerald-600 dark:text-emerald-400" />
                  <Row label="Огласи со добра цена" value={d.good_deal_count.toLocaleString()} />
                  <Row label="Вкупно огласи" value={d.count.toLocaleString()} />
                </div>
              )
            }}
          />
          <Bar dataKey="good_deal_pct" radius={[0, 4, 4, 0]} maxBarSize={20} fill="#10b981" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function SourceComparisonChart({ selected, theme }) {
  const [pazar3Data, setPazar3Data] = useState([])
  const [reklama5Data, setReklama5Data] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'
  const cursorColor = isDark ? '#1e293b80' : '#f8fafc'

  useEffect(() => {
    Promise.all([fetchBrandStats('pazar3'), fetchBrandStats('reklama5')])
      .then(([p, r]) => { setPazar3Data(p); setReklama5Data(r) })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading || error) return null

  const pByKey = Object.fromEntries(pazar3Data.map(b => [b.brand.toLowerCase(), b]))
  const rByKey = Object.fromEntries(reklama5Data.map(b => [b.brand.toLowerCase(), b]))

  const merged = selected
    .map(brand => {
      const key = brand.toLowerCase()
      const p = pByKey[key]
      const r = rByKey[key]
      if (!p && !r) return null
      return { brand, pazar3_avg: p?.avg_price ?? null, reklama5_avg: r?.avg_price ?? null }
    })
    .filter(Boolean)

  if (merged.length === 0) return null

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Споредба на цени по платформа</h2>
      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 mb-4">
        Просечна цена (€) за истиот бренд на Пазар3 наспроти Реклама5
      </p>
      <ResponsiveContainer width="100%" height={Math.max(merged.length * 44 + 40, 140)}>
        <BarChart data={merged} layout="vertical" margin={{ left: 8, right: 32, top: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={v => `€${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}`}
            tick={{ fontSize: 11, fill: axisColor }}
            tickLine={{ stroke: gridColor }}
            axisLine={{ stroke: gridColor }}
          />
          <YAxis dataKey="brand" type="category" width={72} tick={{ fontSize: 12, fill: axisColor }} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ fill: cursorColor }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              return (
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 text-xs shadow-lg min-w-[160px]">
                  <p className="font-semibold text-slate-900 dark:text-slate-100 mb-2">{label}</p>
                  {payload.map(p => p.value != null && (
                    <Row
                      key={p.dataKey}
                      label={p.dataKey === 'pazar3_avg' ? sourceLabel('pazar3') : sourceLabel('reklama5')}
                      value={`€${p.value.toLocaleString()}`}
                      color={p.dataKey === 'pazar3_avg' ? 'text-orange-500' : 'text-sky-500'}
                    />
                  ))}
                </div>
              )
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={v => v === 'pazar3_avg' ? sourceLabel('pazar3') : sourceLabel('reklama5')} />
          <Bar dataKey="pazar3_avg" fill="#f97316" radius={[0, 4, 4, 0]} maxBarSize={14} />
          <Bar dataKey="reklama5_avg" fill="#0ea5e9" radius={[0, 4, 4, 0]} maxBarSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

const COLORS = [
  '#7c3aed', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444',
  '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#8b5cf6',
  '#06b6d4', '#84cc16', '#fb923c', '#34d399', '#60a5fa',
  '#f472b6', '#a78bfa',
]

function PriceTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 text-xs shadow-lg min-w-[160px]">
      <p className="font-semibold text-slate-900 dark:text-slate-100 mb-2">{d.brand}</p>
      <div className="space-y-1">
        <Row label="Огласи" value={d.count.toLocaleString()} />
        <Row label="Просечна" value={`€${d.avg_price.toLocaleString()}`} color="text-violet-600 dark:text-violet-400" />
        <Row label="Медијана" value={`€${d.median_price.toLocaleString()}`} />
        <Row label="Мин" value={`€${d.min_price.toLocaleString()}`} color="text-emerald-600 dark:text-emerald-400" />
        <Row label="Макс" value={`€${d.max_price.toLocaleString()}`} color="text-red-600 dark:text-red-400" />
      </div>
    </div>
  )
}

function SectionHeader({ eyebrow, title, desc }) {
  return (
    <div className="border-b border-slate-100 dark:border-slate-800 pb-3">
      <span className="text-[11px] font-semibold uppercase tracking-widest text-violet-500 dark:text-violet-400">
        {eyebrow}
      </span>
      <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mt-0.5">{title}</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{desc}</p>
    </div>
  )
}

function Row({ label, value, color = 'text-slate-900 dark:text-slate-100' }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className={`font-mono ${color}`}>{value}</span>
    </div>
  )
}

function Chart({ title, data, dataKey, tickFormatter, colorMap, theme }) {
  const isDark = theme === 'dark'
  const axisColor = isDark ? '#64748b' : '#94a3b8'
  const gridColor = isDark ? '#1e293b' : '#f1f5f9'
  const cursorColor = isDark ? '#1e293b80' : '#f8fafc'

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">{title}</h2>
      <ResponsiveContainer width="100%" height={Math.max(data.length * 44 + 20, 100)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 32, top: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: axisColor }}
            tickLine={{ stroke: gridColor }}
            axisLine={{ stroke: gridColor }}
            tickFormatter={tickFormatter}
          />
          <YAxis
            dataKey="brand"
            type="category"
            width={72}
            tick={{ fontSize: 12, fill: axisColor }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<PriceTooltip />} cursor={{ fill: cursorColor }} />
          <Bar dataKey={dataKey} radius={[0, 4, 4, 0]} maxBarSize={28}>
            {data.map((entry) => (
              <Cell key={entry.brand} fill={colorMap[entry.brand] || COLORS[0]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

const PILLS_COLLAPSED_COUNT = 20

export default function AnalyticsPage({ theme }) {
  const [data, setData] = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [pillsExpanded, setPillsExpanded] = useState(false)

  useEffect(() => {
    fetchBrandStats()
      .then(d => {
        setData(d)
        setSelected(d.slice(0, 10).map(b => b.brand))
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  const colorMap = Object.fromEntries(data.map((b, i) => [b.brand, COLORS[i % COLORS.length]]))
  const filtered = data.filter(b => selected.includes(b.brand))
  const byPrice = [...filtered].sort((a, b) => b.avg_price - a.avg_price)
  const byCount = [...filtered].sort((a, b) => b.count - a.count)

  const toggle = brand =>
    setSelected(s => s.includes(brand) ? s.filter(b => b !== brand) : [...s, brand])

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-slate-400 text-sm gap-3">
      <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Се вчитуваат податоци...
    </div>
  )

  if (error) return (
    <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
      Грешка при вчитување. Обиди се повторно.
    </div>
  )

  return (
    <div className="p-6 space-y-12 max-w-7xl mx-auto">

      {/* Section: Activity */}
      <section className="space-y-6">
        <SectionHeader
          eyebrow="Активност"
          title="Скрапирање и пазарна активност"
          desc="Колку нови огласи влегуваат во системот и како се движи пазарот низ времето"
        />
        <ScrapeActivityChart theme={theme} />
        <TrendChart theme={theme} />
      </section>

      {/* Section: Market overview */}
      <section className="space-y-6">
        <SectionHeader
          eyebrow="Преглед"
          title="Категории, цени и состојба"
          desc="Каде е концентриран пазарот и колку губат вредност уредите со употреба"
        />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <CategoryChart theme={theme} />
          <GoodDealChart theme={theme} />
        </div>
        <DepreciationChart theme={theme} />
      </section>

      {/* Section: Brand analysis */}
      <section className="space-y-6">
        <SectionHeader
          eyebrow="Брендови"
          title="Анализа по бренд"
          desc="Споредба на цени и присутност на брендови на македонскиот пазар"
        />

      {/* Brand pills */}
      <div className="flex flex-wrap gap-2">
        {(pillsExpanded ? data : data.slice(0, PILLS_COLLAPSED_COUNT)).map((b, i) => {
          const active = selected.includes(b.brand)
          return (
            <button
              key={b.brand}
              onClick={() => toggle(b.brand)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                active
                  ? 'text-white border-transparent'
                  : 'bg-transparent border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-400'
              }`}
              style={active ? { backgroundColor: COLORS[i % COLORS.length] } : {}}
            >
              {b.brand}
              <span className={`ml-1 ${active ? 'opacity-75' : 'opacity-50'}`}>
                {b.count.toLocaleString()}
              </span>
            </button>
          )
        })}
      </div>

      {data.length > PILLS_COLLAPSED_COUNT && (
        <button
          onClick={() => setPillsExpanded(e => !e)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors -mt-3"
        >
          <svg
            className={`w-3.5 h-3.5 transition-transform ${pillsExpanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
          {pillsExpanded ? 'Прикажи помалку' : `Прикажи ги сите (${data.length})`}
        </button>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-slate-400 text-center py-12">Избери барем еден бренд</p>
      ) : (
        <>
          {/* Charts side by side */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <Chart
              title="Просечна цена (€)"
              data={byPrice}
              dataKey="avg_price"
              tickFormatter={v => `€${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}`}
              colorMap={colorMap}
              theme={theme}
            />
            <Chart
              title="Број на огласи"
              data={byCount}
              dataKey="count"
              tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}
              colorMap={colorMap}
              theme={theme}
            />
          </div>

          <SourceComparisonChart selected={selected} theme={theme} />

          {/* Stats table */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800">
                  {['Бренд', 'Огласи', 'Мин', 'Q1', 'Медијана', 'Просек', 'Q3', 'Макс'].map(h => (
                    <th
                      key={h}
                      className={`px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wider ${h === 'Бренд' ? 'text-left' : 'text-right'}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...filtered].sort((a, b) => b.count - a.count).map(b => (
                  <tr key={b.brand} className="border-b border-slate-50 dark:border-slate-800/50 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: colorMap[b.brand] }} />
                        <span className="font-medium text-slate-900 dark:text-slate-100">{b.brand}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-500 dark:text-slate-400">{b.count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-emerald-600 dark:text-emerald-400">€{b.min_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-slate-500 dark:text-slate-400">€{b.q1.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-slate-900 dark:text-slate-100">€{b.median_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-violet-600 dark:text-violet-400">€{b.avg_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-slate-500 dark:text-slate-400">€{b.q3.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-red-500 dark:text-red-400">€{b.max_price.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      </section>

    </div>
  )
}
