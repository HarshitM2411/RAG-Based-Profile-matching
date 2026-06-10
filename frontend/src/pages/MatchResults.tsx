import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { Icon } from '../components/Icon'
import { MatchScoreRing } from '../components/MatchScoreRing'
import { TopBar } from '../components/TopBar'

function initials(name: string) {
  return name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

const DEFAULT_WEIGHTS = {
  technical: 80,
  domain: 45,
  complexity: 65,
}

export function MatchResults() {
  const { matchResult, jobTitle } = useApp()
  const [query, setQuery] = useState('')
  const [sortBy, setSortBy] = useState<'score' | 'experience'>('score')
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS)
  const [recalcKey, setRecalcKey] = useState(0)

  const matches = useMemo(() => {
    if (!matchResult) return []
    const filtered = matchResult.top_matches.filter((match) => {
      const haystack =
        `${match.candidate_name} ${match.resume_path} ${match.matched_skills.join(' ')}`.toLowerCase()
      return haystack.includes(query.toLowerCase())
    })

    const weightFactor = (weights.technical + weights.domain + weights.complexity) / 300

    return filtered.sort((left, right) => {
      if (sortBy === 'experience') {
        return (right.experience_years ?? 0) - (left.experience_years ?? 0)
      }
      const leftScore = left.match_score * weightFactor
      const rightScore = right.match_score * weightFactor
      return rightScore - leftScore + recalcKey * 0
    })
  }, [matchResult, query, sortBy, weights, recalcKey])

  const skillPriority = useMemo(() => {
    if (!matchResult) return []
    return Array.from(new Set(matchResult.top_matches.flatMap((match) => match.matched_skills))).slice(
      0,
      8,
    )
  }, [matchResult])

  if (!matchResult) {
    return (
      <>
        <TopBar title="Match Results" />
        <main className="ml-[260px] flex min-h-screen items-center justify-center bg-background pt-16">
          <div className="card-elevated max-w-md rounded-[10px] border border-outline-variant bg-surface-container-lowest p-8 text-center">
            <Icon name="query_stats" className="mb-4 text-4xl text-secondary" />
            <h2 className="mb-2 text-xl font-semibold">No match results yet</h2>
            <p className="mb-6 text-sm text-on-surface-variant">
              Run a job match first to see ranked candidates here.
            </p>
            <Link
              to="/matching"
              className="inline-flex rounded-[10px] bg-secondary px-6 py-3 text-sm font-semibold text-on-secondary"
            >
              Go to Job Matching
            </Link>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <TopBar
        title="Match Results"
        badge={jobTitle}
        searchPlaceholder="Search results..."
        searchIconPosition="left"
        searchValue={query}
        onSearchChange={setQuery}
      />
      <main className="ml-[260px] flex min-h-screen bg-background pt-16">
        <div className="custom-scrollbar flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-4xl space-y-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
              <p className="font-medium text-on-surface-variant">
                Found {matches.length} highly relevant candidate{matches.length === 1 ? '' : 's'}
              </p>
              <div className="flex items-center gap-2">
                <span className="text-xs uppercase tracking-wider text-on-surface-variant">Sort by:</span>
                <select
                  className="border-none bg-transparent text-sm font-bold text-secondary focus:ring-0"
                  value={sortBy}
                  onChange={(event) => setSortBy(event.target.value as 'score' | 'experience')}
                >
                  <option value="score">RAG Match Score</option>
                  <option value="experience">Years of Experience</option>
                </select>
              </div>
            </div>

            {matches.map((match) => (
              <div
                key={match.resume_path}
                className="card-elevated rounded-[10px] border border-outline-variant bg-surface-container-lowest p-6 transition-shadow hover:shadow-md"
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary-fixed text-sm font-bold text-on-secondary-fixed">
                      {initials(match.candidate_name)}
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-primary">{match.candidate_name}</h3>
                      <div className="flex items-center gap-2 text-on-surface-variant">
                        <Icon name="description" className="text-[18px]" />
                        <span className="text-sm">{match.resume_path}</span>
                      </div>
                    </div>
                  </div>
                  <MatchScoreRing score={match.match_score} />
                </div>

                <div className="space-y-4">
                  <div>
                    <p className="mb-2 text-xs font-bold uppercase text-on-surface-variant">Matched Skills</p>
                    <div className="flex flex-wrap gap-2">
                      {match.matched_skills.map((skill) => (
                        <span
                          key={skill}
                          className="rounded-full bg-tertiary/10 px-3 py-1 text-xs font-medium text-on-tertiary-container"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-xs font-bold uppercase text-on-surface-variant">
                      Relevant Excerpts
                    </p>
                    {match.relevant_excerpts.map((excerpt) => (
                      <div
                        key={excerpt.slice(0, 24)}
                        className="mb-2 rounded-r-lg border-l-4 border-secondary bg-surface-container-low p-3"
                      >
                        <p className="font-mono text-sm italic text-on-surface-variant">"{excerpt}"</p>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-lg border border-secondary/10 bg-secondary/5 p-4">
                    <div className="mb-1 flex items-center gap-2">
                      <Icon name="psychology" className="text-[18px] text-secondary" />
                      <p className="text-xs font-bold uppercase text-secondary">AI Reasoning</p>
                    </div>
                    <p className="text-sm text-on-surface">{match.reasoning}</p>
                  </div>
                </div>

                <div className="mt-6 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    className="rounded-xl px-4 py-2 font-bold text-secondary transition-all hover:bg-secondary/5"
                  >
                    View Full Resume
                  </button>
                  <button
                    type="button"
                    className="rounded-xl bg-secondary px-6 py-2 font-bold text-on-secondary shadow-sm transition-all hover:opacity-90 active:scale-[0.98]"
                  >
                    Schedule Interview
                  </button>
                </div>
              </div>
            ))}

            {!matches.length ? (
              <p className="text-center text-sm text-on-surface-variant">No candidates match your filter.</p>
            ) : null}
          </div>
        </div>

        <aside className="flex w-80 flex-col border-l border-outline-variant bg-surface">
          <div className="border-b border-outline-variant bg-surface-container-low p-6">
            <div className="mb-2 flex items-center gap-2">
              <Icon name="tune" className="text-secondary" />
              <h3 className="font-bold text-primary">Ranking Weights</h3>
            </div>
            <p className="text-xs text-on-surface-variant">Adjust AI priority for this specific match run.</p>
          </div>
          <div className="flex-1 space-y-8 overflow-y-auto p-6">
            {[
              {
                key: 'technical' as const,
                label: 'Technical Skills',
                hint: 'Prioritizes direct match with required tech stack.',
              },
              {
                key: 'domain' as const,
                label: 'Domain Experience',
                hint: 'Focus on candidates from similar industries.',
              },
              {
                key: 'complexity' as const,
                label: 'Project Complexity',
                hint: 'Matches based on scale of previous work.',
              },
            ].map((item) => (
              <div key={item.key} className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="font-bold text-on-surface">{item.label}</label>
                  <span className="tabular-nums font-bold text-secondary">{weights[item.key]}%</span>
                </div>
                <input
                  className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-surface-container-highest accent-secondary"
                  type="range"
                  min={0}
                  max={100}
                  value={weights[item.key]}
                  onChange={(event) =>
                    setWeights((current) => ({
                      ...current,
                      [item.key]: Number(event.target.value),
                    }))
                  }
                />
                <p className="text-xs text-on-surface-variant">{item.hint}</p>
              </div>
            ))}

            <div className="space-y-4 pt-4">
              <h4 className="text-[11px] font-bold uppercase tracking-widest text-on-surface">
                Skill Priority
              </h4>
              <div className="space-y-2">
                {skillPriority.map((skill, index) => (
                  <label
                    key={skill}
                    className="flex cursor-pointer items-center gap-3 rounded-lg p-2 transition-colors hover:bg-surface-container-high"
                  >
                    <input
                      defaultChecked={index < 2}
                      className="rounded border-outline-variant text-secondary focus:ring-secondary"
                      type="checkbox"
                    />
                    <span className="text-sm">
                      {index < 2 ? 'Required' : 'Preferred'}: {skill}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="border-t border-outline-variant bg-surface-container-low p-6">
            <button
              type="button"
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 font-bold text-on-primary transition-transform active:scale-[0.98]"
              onClick={() => setRecalcKey((key) => key + 1)}
            >
              <Icon name="refresh" className="text-[20px]" />
              Recalculate Ranking
            </button>
          </div>
        </aside>
      </main>
    </>
  )
}
