import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../context/AppContext'
import { Icon } from '../components/Icon'
import { TopBar } from '../components/TopBar'
import type { JdRequirements } from '../types'

const LOADING_STATUSES = [
  'Querying vector store...',
  'Scoring candidates...',
  'Ranking by strict requirements...',
  'Generating match summaries...',
]

function inferSeniority(jobDescription: string) {
  if (/senior|lead|principal|staff/i.test(jobDescription)) return 'Senior / Lead'
  if (/junior|entry|graduate/i.test(jobDescription)) return 'Junior / Entry'
  if (/mid[- ]?level|intermediate/i.test(jobDescription)) return 'Mid-Level'
  return 'Not specified'
}

function inferLocation(jobDescription: string) {
  if (/remote/i.test(jobDescription) && /hybrid/i.test(jobDescription)) return 'Remote / Hybrid'
  if (/remote/i.test(jobDescription)) return 'Remote'
  if (/hybrid/i.test(jobDescription)) return 'Hybrid'
  if (/on[- ]site|in[- ]office/i.test(jobDescription)) return 'On-site'
  return 'Not specified'
}

export function JobMatching() {
  const navigate = useNavigate()
  const { setMatchResult, addSearchHistory, setJobTitle, searchHistory } = useApp()
  const [jobDescription, setJobDescription] = useState('')
  const [topK, setTopK] = useState(10)
  const [strictFilter, setStrictFilter] = useState(true)
  const [vectorOnlySearch, setVectorOnlySearch] = useState(false)
  const [requirements, setRequirements] = useState<JdRequirements | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingStatus, setLoadingStatus] = useState(LOADING_STATUSES[0])
  const [error, setError] = useState('')
  const [resumeCount, setResumeCount] = useState(0)

  useEffect(() => {
    api.getDashboard().then((stats) => setResumeCount(stats.indexed_resumes || stats.total_resumes))
  }, [])

  useEffect(() => {
    if (!jobDescription.trim()) {
      setRequirements(null)
      return
    }

    const timer = window.setTimeout(() => {
      api
        .parseJd(jobDescription)
        .then(setRequirements)
        .catch(() => setRequirements(null))
    }, 400)

    return () => window.clearTimeout(timer)
  }, [jobDescription])

  const runMatch = async () => {
    if (!jobDescription.trim()) {
      setError('Paste a job description before searching.')
      return
    }

    setLoading(true)
    setError('')
    setLoadingStatus(LOADING_STATUSES[0])

    let statusIndex = 0
    const statusTimer = window.setInterval(() => {
      statusIndex = Math.min(statusIndex + 1, LOADING_STATUSES.length - 1)
      setLoadingStatus(LOADING_STATUSES[statusIndex])
    }, 1200)

    try {
      const result = await api.match(jobDescription, topK)
      window.clearInterval(statusTimer)
      setMatchResult(result)

      const title =
        jobDescription
          .split('\n')[0]
          .replace(/^we are looking for\s*/i, '')
          .slice(0, 48) || 'Job Match'
      setJobTitle(title)
      addSearchHistory({
        id: crypto.randomUUID(),
        title,
        timestamp: new Date().toISOString(),
        matchCount: result.top_matches.length,
      })
      navigate('/results')
    } catch (err) {
      window.clearInterval(statusTimer)
      setError(err instanceof Error ? err.message : 'Matching failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <TopBar title="Job Matching Engine" />
      <main className="ml-[260px] min-h-screen pt-16">
        <section className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto grid max-w-[1440px] grid-cols-12 gap-5">
            <div className="col-span-12 space-y-6 lg:col-span-8">
              <div className="card-elevated rounded-[10px] border border-outline-variant bg-surface-container-lowest p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="flex items-center gap-2 text-lg font-semibold">
                    <Icon name="description" className="text-secondary" />
                    Job Description
                  </h2>
                  <button
                    type="button"
                    className="text-xs font-medium text-secondary hover:underline"
                    onClick={() => setJobDescription('')}
                  >
                    Clear Canvas
                  </button>
                </div>
                <textarea
                  className="min-h-[300px] w-full resize-none rounded-lg border border-outline-variant bg-surface-container-low p-4 text-sm outline-none transition-all focus:border-secondary focus:ring-2 focus:ring-secondary/20"
                  placeholder={`Paste the full job description here (Responsibilities, Requirements, Benefits)...

Example: We are looking for a Senior ML Engineer with 5+ years of experience in Python and PyTorch. Experience with RAG architectures and Vector Databases (Pinecone/Milvus) is highly desirable...`}
                  value={jobDescription}
                  onChange={(event) => setJobDescription(event.target.value)}
                />
                <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
                  <div className="flex flex-wrap gap-4">
                    <div className="flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container px-3 py-1.5 text-xs">
                      <Icon name="attach_file" className="text-sm" />
                      Upload PDF/Docx
                    </div>
                    <div className="flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container px-3 py-1.5 text-xs">
                      <Icon name="link" className="text-sm" />
                      Import from URL
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={loading}
                    className="flex items-center gap-2 rounded-[10px] bg-secondary px-8 py-3 font-semibold text-on-secondary shadow-md transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-60"
                    onClick={() => void runMatch()}
                  >
                    <Icon name="spark" />
                    Find Top Matches
                  </button>
                </div>
              </div>

              <div className="card-elevated rounded-[10px] border border-outline-variant bg-surface-container-lowest p-6">
                <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold">
                  <Icon name="analytics" className="text-tertiary-fixed-dim" />
                  Requirement Insights
                </h3>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <p className="mb-2 text-xs uppercase tracking-wide text-on-surface-variant">
                      Required Skills
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {(requirements?.required_skills ?? []).map((skill) => (
                        <span
                          key={skill}
                          className="rounded-full border border-secondary/20 bg-secondary/10 px-3 py-1 text-xs text-secondary"
                        >
                          {skill}
                        </span>
                      ))}
                      {!requirements?.required_skills?.length ? (
                        <span className="text-sm text-on-surface-variant">
                          Skills appear as you type a job description.
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div>
                    <p className="mb-2 text-xs uppercase tracking-wide text-on-surface-variant">
                      Extracted Metadata
                    </p>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center justify-between border-b border-outline-variant pb-1">
                        <span className="text-on-surface-variant">Experience</span>
                        <span className="font-bold">
                          {requirements?.min_experience_years
                            ? `${requirements.min_experience_years}+ Years`
                            : 'Not specified'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between border-b border-outline-variant pb-1">
                        <span className="text-on-surface-variant">Seniority</span>
                        <span className="font-bold">
                          {jobDescription.trim() ? inferSeniority(jobDescription) : 'Not specified'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between border-b border-outline-variant pb-1">
                        <span className="text-on-surface-variant">Location</span>
                        <span className="font-bold">
                          {jobDescription.trim() ? inferLocation(jobDescription) : 'Not specified'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {error ? (
                <div className="rounded-xl border border-error-container bg-error-container/40 p-4 text-sm text-on-error-container">
                  {error}
                </div>
              ) : null}
            </div>

            <div className="col-span-12 space-y-6 lg:col-span-4">
              <div className="card-elevated rounded-[10px] border border-outline-variant bg-surface-container-lowest p-6">
                <h3 className="mb-6 flex items-center gap-2 text-lg font-semibold">
                  <Icon name="tune" />
                  Matching Parameters
                </h3>
                <div className="mb-8 space-y-4">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">Top K Results</label>
                    <span className="tabular-nums text-lg font-bold text-secondary">{topK}</span>
                  </div>
                  <input
                    className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-surface-container accent-secondary"
                    type="range"
                    min={1}
                    max={20}
                    value={topK}
                    onChange={(event) => setTopK(Number(event.target.value))}
                  />
                  <div className="flex justify-between text-[10px] uppercase tracking-tighter text-on-surface-variant">
                    <span>Precision</span>
                    <span>Recall Focus</span>
                  </div>
                </div>
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium">Strict filtering</span>
                      <p className="text-xs text-on-surface-variant">Only "Must-have" skills</p>
                    </div>
                    <label className="relative inline-flex cursor-pointer items-center">
                      <input
                        className="peer sr-only"
                        type="checkbox"
                        checked={strictFilter}
                        onChange={(event) => setStrictFilter(event.target.checked)}
                      />
                      <div className="peer h-6 w-11 rounded-full bg-surface-variant after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all peer-checked:bg-secondary peer-checked:after:translate-x-full" />
                    </label>
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium">Vector-only search</span>
                      <p className="text-xs text-on-surface-variant">Ignore keyword overlap</p>
                    </div>
                    <label className="relative inline-flex cursor-pointer items-center">
                      <input
                        className="peer sr-only"
                        type="checkbox"
                        checked={vectorOnlySearch}
                        onChange={(event) => setVectorOnlySearch(event.target.checked)}
                      />
                      <div className="peer h-6 w-11 rounded-full bg-surface-variant after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all peer-checked:bg-secondary peer-checked:after:translate-x-full" />
                    </label>
                  </div>
                </div>
                <hr className="my-6 border-outline-variant" />
                <div className="rounded-lg border border-tertiary-fixed/30 bg-tertiary-fixed/10 p-4">
                  <div className="flex gap-3">
                    <Icon name="info" className="text-on-tertiary-container" />
                    <p className="text-xs text-on-tertiary-container">
                      Your current selection will query against{' '}
                      <strong>{resumeCount.toLocaleString()}</strong> indexed resumes in the{' '}
                      <strong>resumes</strong> collection.
                    </p>
                  </div>
                </div>
              </div>

              <div className="card-elevated rounded-[10px] border border-outline-variant bg-surface-container-lowest p-6">
                <h3 className="mb-4 text-xs uppercase tracking-widest text-on-surface-variant">
                  Recent Searches
                </h3>
                <div className="space-y-3">
                  {searchHistory.map((entry) => (
                    <div
                      key={entry.id}
                      className="cursor-pointer rounded-lg border border-outline-variant/30 bg-surface-container-low p-3 transition-colors hover:bg-surface-container"
                    >
                      <p className="truncate text-sm font-medium">{entry.title}</p>
                      <p className="mt-1 text-[10px] uppercase text-on-surface-variant">
                        {new Date(entry.timestamp).toLocaleString()} • {entry.matchCount} matches
                      </p>
                    </div>
                  ))}
                  {!searchHistory.length ? (
                    <p className="text-sm text-on-surface-variant">No searches yet.</p>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {loading ? (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-white/80 p-6 backdrop-blur-sm">
          <div className="flex w-full max-w-2xl flex-col items-center rounded-2xl border border-outline-variant bg-white p-10 shadow-xl">
            <div className="mb-8 h-16 w-16 animate-spin rounded-full border-4 border-secondary/20 border-t-secondary" />
            <h3 className="mb-2 text-center text-2xl font-semibold text-primary">{loadingStatus}</h3>
            <p className="mb-10 text-center text-sm text-on-surface-variant">
              Comparing semantic embeddings against {resumeCount.toLocaleString()}+ talent profiles.
            </p>
            <div className="w-full space-y-4">
              <div className="skeleton-pulse h-16 w-full rounded-lg" />
              <div className="skeleton-pulse h-16 w-full rounded-lg opacity-60" />
              <div className="skeleton-pulse h-16 w-full rounded-lg opacity-30" />
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
