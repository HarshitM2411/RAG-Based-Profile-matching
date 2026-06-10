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

export function MatchResults() {
  const { matchResult, jobTitle } = useApp()
  const [query, setQuery] = useState('')
  const [sortBy, setSortBy] = useState<'score' | 'experience'>('score')

  const matches = useMemo(() => {
    if (!matchResult) return []
    const filtered = matchResult.top_matches.filter((match) => {
      const haystack = `${match.candidate_name} ${match.resume_path} ${match.matched_skills.join(' ')}`.toLowerCase()
      return haystack.includes(query.toLowerCase())
    })
    return filtered.sort((left, right) => {
      if (sortBy === 'experience') {
        return (right.experience_years ?? 0) - (left.experience_years ?? 0)
      }
      return right.match_score - left.match_score
    })
  }, [matchResult, query, sortBy])

  const avgScore =
    matches.length > 0
      ? Math.round(matches.reduce((sum, match) => sum + match.match_score, 0) / matches.length)
      : 0

  const exportJson = () => {
    if (!matchResult) return
    const blob = new Blob([JSON.stringify(matchResult, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'match-results.json'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  if (!matchResult) {
    return (
      <>
        <TopBar title="Match Results" />
        <main className="ml-[260px] flex min-h-screen items-center justify-center pt-16">
          <div className="max-w-md rounded-xl border border-outline-variant bg-surface-container-lowest p-8 text-center">
            <Icon name="query_stats" className="mb-4 text-4xl text-secondary" />
            <h2 className="mb-2 text-xl font-semibold">No match results yet</h2>
            <p className="mb-6 text-sm text-on-surface-variant">
              Run a job match first to see ranked candidates here.
            </p>
            <Link
              to="/matching"
              className="inline-flex rounded-lg bg-secondary px-6 py-3 text-sm font-semibold text-on-secondary"
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
      <TopBar title="Match Results" badge={jobTitle} searchPlaceholder="Search results..." />
      <main className="ml-[260px] flex min-h-screen pt-16">
        <div className="custom-scrollbar flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-4xl space-y-6">
            <div className="sticky top-0 z-10 rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-on-surface-variant">
                    Found {matches.length} relevant candidates • Avg score {avgScore}
                  </p>
                  <p className="mt-1 line-clamp-1 text-xs text-on-surface-variant">
                    {matchResult.job_description.slice(0, 120)}...
                  </p>
                </div>
                <button
                  type="button"
                  className="rounded-lg border border-outline-variant px-4 py-2 text-sm font-medium text-secondary hover:bg-secondary/5"
                  onClick={exportJson}
                >
                  Export JSON
                </button>
              </div>
            </div>

            <div className="mb-4 flex items-center justify-between">
              <input
                className="w-64 rounded-lg border border-outline-variant bg-surface-container-low px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-secondary/20"
                placeholder="Filter candidates..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
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

            {matches.map((match, index) => (
              <div
                key={match.resume_path}
                className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary-fixed text-sm font-bold text-on-secondary-fixed">
                      {index < 3 ? `#${index + 1}` : initials(match.candidate_name)}
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
                    <p className="mb-2 text-xs font-bold uppercase text-on-surface-variant">Relevant Excerpts</p>
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
                    Shortlist
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
            <p className="text-xs text-on-surface-variant">Score formula used by the RAG engine.</p>
          </div>
          <div className="flex-1 space-y-8 overflow-y-auto p-6">
            {[
              { label: 'Semantic Similarity', value: '50%', hint: 'Vector similarity between JD and resume chunks.' },
              { label: 'Skill Overlap', value: '30%', hint: 'Required skills found in candidate profile.' },
              { label: 'Experience Fit', value: '20%', hint: 'Candidate years vs minimum requirement.' },
            ].map((item) => (
              <div key={item.label} className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="font-bold text-on-surface">{item.label}</label>
                  <span className="font-bold text-secondary">{item.value}</span>
                </div>
                <p className="text-xs text-on-surface-variant">{item.hint}</p>
              </div>
            ))}

            <div className="space-y-2">
              <h4 className="text-[11px] font-bold uppercase tracking-widest text-on-surface">
                Required Skills
              </h4>
              {Array.from(
                new Set(matchResult.top_matches.flatMap((match) => match.matched_skills)),
              ).map((skill) => (
                <label
                  key={skill}
                  className="flex cursor-pointer items-center gap-3 rounded-lg p-2 transition-colors hover:bg-surface-container-high"
                >
                  <input defaultChecked className="rounded border-outline-variant text-secondary focus:ring-secondary" type="checkbox" />
                  <span className="text-sm">{skill}</span>
                </label>
              ))}
            </div>
          </div>
        </aside>
      </main>
    </>
  )
}
