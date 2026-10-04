import { CONDITIONS } from '../utils/conditions'

// Condition as plain text after the source, joined with a dash: "• Пазар3 – Нов"
export default function ConditionTag({ condition }) {
  if (!condition) return null
  return (
    <span className="-ml-1 font-medium text-slate-500 dark:text-slate-400">
      – {CONDITIONS[condition]?.label || condition}
    </span>
  )
}
