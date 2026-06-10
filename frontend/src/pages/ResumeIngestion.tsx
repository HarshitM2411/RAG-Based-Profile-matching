import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { Icon } from '../components/Icon'
import { TopBar } from '../components/TopBar'
import type { ResumeFile } from '../types'

const PIPELINE_STEPS = [
  'Load Files',
  'Extract Text & Metadata',
  'Section Chunking',
  'Generate Embeddings',
  'Store in ChromaDB',
]

function fileIcon(format: string) {
  if (format === 'PDF') return { icon: 'picture_as_pdf', color: 'text-error' }
  if (format === 'DOCX') return { icon: 'description', color: 'text-secondary' }
  return { icon: 'article', color: 'text-on-surface-variant' }
}

function statusBadge(status: ResumeFile['status']) {
  if (status === 'indexed') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-tertiary-fixed px-2.5 py-1 text-xs font-medium text-on-tertiary-fixed">
        <span className="h-1.5 w-1.5 rounded-full bg-on-tertiary-container" />
        Indexed
      </span>
    )
  }
  if (status === 'processing') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary-fixed px-2.5 py-1 text-xs font-medium text-on-secondary-fixed">
        Processing
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-error-container px-2.5 py-1 text-xs font-medium text-on-error-container">
        <Icon name="error" className="text-[14px]" />
        Failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-container px-2.5 py-1 text-xs font-medium text-on-surface-variant">
      Pending
    </span>
  )
}

export function ResumeIngestion() {
  const [resumes, setResumes] = useState<ResumeFile[]>([])
  const [successMessage, setSuccessMessage] = useState('')
  const [error, setError] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [activeStep, setActiveStep] = useState(-1)
  const [logs, setLogs] = useState<string[]>([])
  const [lastUpdate, setLastUpdate] = useState('—')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const appendLog = useCallback((line: string) => {
    setLogs((current) => [...current.slice(-20), line])
  }, [])

  const loadResumes = useCallback(async () => {
    const response = await api.getResumes()
    setResumes(response.resumes)
  }, [])

  useEffect(() => {
    loadResumes().catch((err: Error) => setError(err.message))
    api.getDashboard().then((stats) => {
      if (stats.last_ingestion) {
        setLastUpdate(new Date(stats.last_ingestion).toLocaleString())
      }
    })
  }, [loadResumes])

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return
    setError('')
    try {
      await api.uploadResumes(Array.from(files))
      appendLog(`[INFO] Uploaded ${files.length} file(s) to resumes/`)
      await loadResumes()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    }
  }

  const runIngestion = async () => {
    setIngesting(true)
    setError('')
    setSuccessMessage('')
    setActiveStep(0)
    appendLog('[INFO] Initializing ingestion pipeline...')

    const stepTimer = window.setInterval(() => {
      setActiveStep((step) => Math.min(step + 1, PIPELINE_STEPS.length - 1))
    }, 1200)

    try {
      const result = await api.ingest()
      window.clearInterval(stepTimer)
      setActiveStep(PIPELINE_STEPS.length)
      setSuccessMessage(result.message)
      appendLog(`[INFO] ${result.message}`)
      setLastUpdate(new Date().toLocaleString())
      await loadResumes()
      setResumes((current) =>
        current.map((resume) => ({ ...resume, status: 'indexed' as const })),
      )
    } catch (err) {
      window.clearInterval(stepTimer)
      const message = err instanceof Error ? err.message : 'Ingestion failed'
      setError(message)
      appendLog(`[ERROR] ${message}`)
      setActiveStep(-1)
    } finally {
      setIngesting(false)
    }
  }

  return (
    <>
      <TopBar title="Resume Ingestion Pipeline" searchPlaceholder="Search ingested files..." />
      <main className="ml-[260px] min-h-screen pt-16">
        <div className="mx-auto max-w-[1440px] p-6">
          {successMessage ? (
            <div className="mb-8 flex items-center justify-between rounded-xl border border-on-tertiary-container/10 bg-tertiary-fixed p-4 text-on-tertiary-fixed">
              <div className="flex items-center gap-3">
                <Icon name="check_circle" />
                <span className="font-medium">{successMessage}</span>
              </div>
              <button type="button" onClick={() => setSuccessMessage('')}>
                <Icon name="close" />
              </button>
            </div>
          ) : null}

          {error ? (
            <div className="mb-6 rounded-xl border border-error-container bg-error-container/40 p-4 text-sm text-on-error-container">
              {error}
            </div>
          ) : null}

          <div className="grid grid-cols-12 gap-5">
            <div className="col-span-12 space-y-5 lg:col-span-8">
              <div
                className="group flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-outline-variant bg-surface-container-lowest p-10 text-center transition-all hover:border-secondary"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault()
                  void handleFiles(event.dataTransfer.files)
                }}
              >
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-secondary-fixed transition-transform group-hover:scale-110">
                  <Icon name="cloud_upload" className="text-[32px] text-secondary" />
                </div>
                <h3 className="mb-2 text-lg font-semibold">Drag and drop resumes here</h3>
                <p className="mb-6 max-w-sm text-on-surface-variant">
                  Support for PDF, DOCX, and TXT files. Up to 50 files per batch.
                </p>
                <button
                  type="button"
                  className="rounded-lg bg-secondary px-8 py-3 font-medium text-on-secondary transition-all hover:opacity-90 active:scale-[0.98]"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Select Files from Computer
                </button>
                <input
                  ref={fileInputRef}
                  className="hidden"
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt"
                  onChange={(event) => void handleFiles(event.target.files)}
                />
              </div>

              <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest">
                <div className="flex items-center justify-between border-b border-outline-variant px-6 py-4">
                  <h3 className="text-lg font-semibold">Current Ingestion Batch</h3>
                  <button
                    type="button"
                    className="text-sm font-medium text-secondary hover:underline"
                    onClick={() => setResumes([])}
                  >
                    Clear List
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead className="bg-surface-container-low text-xs uppercase tracking-wider text-on-surface-variant">
                      <tr>
                        <th className="px-6 py-3 font-semibold">File Name</th>
                        <th className="px-6 py-3 font-semibold">Candidate</th>
                        <th className="px-6 py-3 font-semibold">Skills</th>
                        <th className="px-6 py-3 font-semibold">Exp.</th>
                        <th className="px-6 py-3 font-semibold">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant">
                      {resumes.map((resume) => {
                        const icon = fileIcon(resume.format)
                        return (
                          <tr key={resume.file_path} className="transition-colors hover:bg-surface-container-low">
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <Icon name={icon.icon} className={icon.color} />
                                <div>
                                  <p className="font-medium">{resume.file_name}</p>
                                  <p className="text-xs text-on-surface-variant">{resume.size_kb} KB</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4 font-medium">{resume.candidate_name}</td>
                            <td className="px-6 py-4">
                              <div className="flex flex-wrap gap-1">
                                {resume.skills.map((skill) => (
                                  <span
                                    key={skill}
                                    className="rounded bg-secondary-fixed px-2 py-0.5 text-xs text-on-secondary-fixed"
                                  >
                                    {skill}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              {resume.experience_years != null && resume.experience_years >= 0
                                ? `${resume.experience_years} yrs`
                                : '—'}
                            </td>
                            <td className="px-6 py-4">{statusBadge(resume.status)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  {!resumes.length ? (
                    <p className="px-6 py-8 text-center text-sm text-on-surface-variant">
                      No resumes uploaded yet. Drop files to get started.
                    </p>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="col-span-12 space-y-5 lg:col-span-4">
              <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6">
                <button
                  type="button"
                  disabled={ingesting}
                  className="flex w-full items-center justify-center gap-3 rounded-lg bg-primary py-4 text-lg font-semibold text-on-primary transition-all hover:bg-on-primary-fixed-variant active:scale-[0.98] disabled:opacity-60"
                  onClick={() => void runIngestion()}
                >
                  <Icon name="database" />
                  Build / Update Vector Store
                </button>
                <div className="mt-4 flex items-center justify-between text-xs text-on-surface-variant">
                  <span>
                    ChromaDB State:{' '}
                    <span className="font-bold text-tertiary-fixed-dim">
                      {ingesting ? 'BUILDING' : 'READY'}
                    </span>
                  </span>
                  <span>Last update: {lastUpdate}</span>
                </div>
              </div>

              <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6">
                <h3 className="mb-6 text-lg font-semibold">Pipeline Progress</h3>
                <div className="space-y-6">
                  {PIPELINE_STEPS.map((step, index) => {
                    const done = activeStep > index
                    const active = activeStep === index
                    return (
                      <div key={step} className="flex gap-4">
                        <div className="flex flex-col items-center">
                          <div
                            className={`flex h-8 w-8 items-center justify-center rounded-full ${
                              done
                                ? 'bg-tertiary-fixed text-on-tertiary-fixed'
                                : active
                                  ? 'bg-secondary text-on-secondary'
                                  : 'border border-outline-variant bg-surface-container-high text-on-surface-variant'
                            }`}
                          >
                            {done ? <Icon name="check" className="text-[18px]" /> : index + 1}
                          </div>
                          {index < PIPELINE_STEPS.length - 1 ? (
                            <div
                              className={`mt-2 h-full w-0.5 ${done ? 'bg-tertiary-fixed' : 'bg-outline-variant'}`}
                            />
                          ) : null}
                        </div>
                        <div className="pb-6">
                          <p className={`font-medium ${active ? 'text-secondary' : ''}`}>{step}</p>
                          {active && ingesting ? (
                            <div className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-surface-container-high">
                              <div className="h-full w-2/3 animate-pulse bg-secondary" />
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="overflow-hidden rounded-xl bg-primary-container p-4 font-mono text-[13px]">
                <div className="mb-3 flex items-center justify-between border-b border-on-primary-fixed-variant/20 pb-2">
                  <span className="flex items-center gap-2 text-xs text-on-primary-container">
                    <span className="h-2 w-2 animate-ping rounded-full bg-tertiary-fixed-dim" />
                    LIVE_LOG.TXT
                  </span>
                </div>
                <div className="custom-scrollbar h-48 space-y-1 overflow-y-auto text-on-primary-container/80">
                  {logs.map((line, index) => (
                    <p key={`${line}-${index}`}>{line}</p>
                  ))}
                  {!logs.length ? <p className="text-on-primary-container/40">Waiting for pipeline...</p> : null}
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}
