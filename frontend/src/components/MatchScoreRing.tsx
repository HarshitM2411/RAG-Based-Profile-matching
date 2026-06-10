export function MatchScoreRing({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score))
  const offset = 100 - clamped
  const color =
    clamped >= 80 ? 'text-tertiary-fixed-dim' : clamped >= 50 ? 'text-amber-500' : 'text-error'

  return (
    <div className="relative h-16 w-16">
      <svg className="match-ring h-full w-full" viewBox="0 0 36 36">
        <circle
          className="text-surface-container-highest"
          cx="18"
          cy="18"
          fill="transparent"
          r="16"
          stroke="currentColor"
          strokeWidth="3"
        />
        <circle
          className={color}
          cx="18"
          cy="18"
          fill="transparent"
          r="16"
          stroke="currentColor"
          strokeDasharray="100"
          strokeDashoffset={offset}
          strokeLinecap="round"
          strokeWidth="3"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-sm font-bold ${color}`}>{Math.round(clamped)}%</span>
        <span className="text-[8px] font-bold uppercase tracking-tighter text-on-surface-variant">
          Match
        </span>
      </div>
    </div>
  )
}
