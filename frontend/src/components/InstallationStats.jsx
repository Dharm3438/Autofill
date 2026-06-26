import { CheckCircle2, Clock, Circle, Layers } from 'lucide-react'

// Shared installation summary cards, used on the Installations page and Dashboard.
const CARDS = [
  { key: 'completed', label: 'Completed', Icon: CheckCircle2,
    cls: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300' },
  { key: 'in_progress', label: 'In Progress', Icon: Clock,
    cls: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300' },
  { key: 'not_started', label: 'Not Started', Icon: Circle,
    cls: 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400' },
  { key: 'total_customers', label: 'Total Customers', Icon: Layers,
    cls: 'bg-[#1a3a2a]/10 text-[#1a3a2a] dark:bg-emerald-500/15 dark:text-emerald-400' },
]

export default function InstallationStats({ summary }) {
  const s = summary || {}
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {CARDS.map(({ key, label, Icon, cls }) => (
        <div
          key={key}
          className="bg-white dark:bg-[#16201b] rounded-2xl border border-gray-200 dark:border-white/10 p-5 shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${cls}`}>
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 leading-none">
                {s[key] ?? 0}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{label}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
