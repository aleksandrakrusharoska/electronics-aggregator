import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import { fetchBrandStats, fetchDepreciation } from '../api/client'

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
      <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Депрецијација по состојба</h2>
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

export default function AnalyticsPage({ theme }) {
  const [data, setData] = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

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
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <DepreciationChart theme={theme} />

      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Анализа по бренд</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Споредба на цени и присутност на брендови на македонскиот пазар
        </p>
      </div>

      {/* Brand pills */}
      <div className="flex flex-wrap gap-2">
        {data.map((b, i) => {
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
    </div>
  )
}
