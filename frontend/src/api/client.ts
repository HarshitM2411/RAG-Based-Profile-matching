import type { DashboardStats, JdRequirements, MatchResult, ResumeFile } from '../types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail || 'Request failed')
  }
  return response.json() as Promise<T>
}

export const api = {
  getDashboard: () => request<DashboardStats>('/api/dashboard'),
  getResumes: () => request<{ resumes: ResumeFile[] }>('/api/resumes'),
  uploadResumes: (files: File[]) => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return request<{ saved: string[]; count: number }>('/api/resumes/upload', {
      method: 'POST',
      body: formData,
    })
  },
  ingest: () =>
    request<{
      success: boolean
      message: string
      chunks_stored: number
      resumes_indexed: number
    }>('/api/ingest', { method: 'POST' }),
  parseJd: (jobDescription: string) =>
    request<JdRequirements>('/api/parse-jd', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_description: jobDescription }),
    }),
  match: (jobDescription: string, topK: number) =>
    request<MatchResult>('/api/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_description: jobDescription, top_k: topK }),
    }),
}
