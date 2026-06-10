import { Icon } from './Icon'

interface TopBarProps {
  title: string
  badge?: string
  searchPlaceholder?: string
}

export function TopBar({
  title,
  badge,
  searchPlaceholder = 'Quick search...',
}: TopBarProps) {
  return (
    <header className="fixed right-0 top-0 z-40 flex h-16 w-[calc(100%-260px)] items-center justify-between border-b border-outline-variant bg-surface px-6">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold text-primary">{title}</h2>
        {badge ? (
          <span className="rounded-full bg-secondary-container/20 px-3 py-1 text-xs font-bold text-secondary">
            {badge}
          </span>
        ) : null}
      </div>

      <div className="flex items-center gap-6">
        <div className="relative">
          <input
            className="w-64 rounded-lg border border-outline-variant bg-surface-container-low px-4 py-1.5 text-sm outline-none transition-all focus:border-secondary focus:ring-2 focus:ring-secondary/20"
            placeholder={searchPlaceholder}
            type="text"
          />
          <Icon
            name="search"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-on-surface-variant"
          />
        </div>
        <button className="rounded-full p-2 transition-all hover:bg-surface-container-high" type="button">
          <Icon name="notifications" />
        </button>
        <button className="rounded-full p-2 transition-all hover:bg-surface-container-high" type="button">
          <Icon name="account_circle" />
        </button>
      </div>
    </header>
  )
}
