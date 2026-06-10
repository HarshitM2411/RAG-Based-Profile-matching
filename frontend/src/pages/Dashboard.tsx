import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Icon } from '../components/Icon'
import { TopBar } from '../components/TopBar'
import type { DashboardStats } from '../types'

function formatTimestamp(value: string | null) {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

function statusLabel(status: DashboardStats['vector_store_status']) {
  if (status === 'connected') return { text: 'Connected', className: 'bg-tertiary-fixed text-on-tertiary-fixed' }
  if (status === 'error') return { text: 'Error', className: 'bg-error-container text-on-error-container' }
  return { text: 'Not Built', className: 'bg-amber-100 text-amber-700' }
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .getDashboard()
      .then(setStats)
      .catch((err: Error) => setError(err.message))
  }, [])

  const status = stats ? statusLabel(stats.vector_store_status) : null

  return (
    <>
      <TopBar title="Dashboard" searchPlaceholder="Search activity..." />
      <main className="ml-[260px] min-h-screen pt-16">
        <div className="mx-auto max-w-[1440px] p-6">
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight text-primary">TalentMatch RAG</h1>
            <p className="mt-1 text-on-surface-variant">
              Semantic resume matching engine — system overview and quick actions
            </p>
          </div>

          {error ? (
            <div className="mb-6 rounded-xl border border-error-container bg-error-container/40 p-4 text-sm text-on-error-container">
              {error}
            </div>
          ) : null}

          <div className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            {[
              { label: 'Total Resumes', value: stats?.total_resumes ?? '—', icon: 'folder_open' },
              { label: 'Chunks in Vector Store', value: stats?.total_chunks ?? '—', icon: 'data_object' },
              {
                label: 'Vector Store Status',
                value: status?.text ?? '—',
                icon: 'database',
                badge: status?.className,
              },
              {
                label: 'Last Ingestion',
                value: formatTimestamp(stats?.last_ingestion ?? null),
                icon: 'schedule',
                small: true,
              },
            ].map((card) => (
              <div
                key={card.label}
                className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm"
              >
                <div className="mb-4 flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wide text-on-surface-variant">
                    {card.label}
                  </span>
                  <Icon name={card.icon} className="text-secondary" />
                </div>
                {card.badge ? (
                  <span className={`inline-flex rounded-full px-3 py-1 text-sm font-bold ${card.badge}`}>
                    {card.value}
                  </span>
                ) : (
                  <p className={`font-bold text-primary ${card.small ? 'text-sm' : 'text-3xl'}`}>
                    {card.value}
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="mb-8 flex flex-wrap gap-4">
            <Link
              to="/ingestion"
              className="inline-flex items-center gap-2 rounded-lg bg-secondary px-6 py-3 text-sm font-semibold text-on-secondary shadow-sm transition-all hover:opacity-90 active:scale-[0.98]"
            >
              <Icon name="upload_file" />
              Upload Resumes
            </Link>
            <Link
              to="/matching"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container-lowest px-6 py-3 text-sm font-semibold text-primary transition-all hover:bg-surface-container-low"
            >
              <Icon name="query_stats" />
              Run Job Match
            </Link>
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 lg:col-span-2">
              <h3 className="mb-4 text-lg font-semibold text-primary">Recent Activity</h3>
              <div className="space-y-3">
                {(stats?.recent_activity ?? []).map((item, index) => (
                  <div
                    key={`${item.type}-${index}`}
                    className="flex items-center justify-between rounded-lg border border-outline-variant/50 bg-surface-container-low px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <Icon name={item.type === 'ingestion' ? 'upload_file' : 'search'} className="text-secondary" />
                      <span className="text-sm font-medium">{item.label}</span>
                    </div>
                    <span className="text-xs text-on-surface-variant">
                      {formatTimestamp(item.timestamp)}
                    </span>
                  </div>
                ))}
                {!stats?.recent_activity?.length ? (
                  <p className="text-sm text-on-surface-variant">No recent activity yet.</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6">
              <h3 className="mb-4 text-lg font-semibold text-primary">System Config</h3>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full bg-secondary/10 px-3 py-1 text-xs font-medium text-secondary">
                  {stats?.embedding_model ?? 'text-embedding-3-small'}
                </span>
                <span className="rounded-full bg-secondary/10 px-3 py-1 text-xs font-medium text-secondary">
                  Collection: {stats?.collection_name ?? 'resumes'}
                </span>
                <span className="rounded-full bg-tertiary-fixed/20 px-3 py-1 text-xs font-medium text-on-tertiary-container">
                  LLM: {stats?.llm_model ?? 'Groq'}
                </span>
                <span className="rounded-full bg-surface-container px-3 py-1 text-xs font-medium text-on-surface-variant">
                  Indexed: {stats?.indexed_resumes ?? 0} resumes
                </span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}
