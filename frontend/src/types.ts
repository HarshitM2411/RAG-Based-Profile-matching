export interface DashboardStats {
  total_resumes: number
  indexed_resumes: number
  total_chunks: number
  vector_store_status: 'connected' | 'not_built' | 'error'
  last_ingestion: string | null
  embedding_model: string
  collection_name: string
  llm_model: string
  recent_activity: Array<{
    type: string
    label: string
    timestamp: string | null
  }>
}

export interface ResumeFile {
  file_name: string
  file_path: string
  size_kb: number
  format: string
  candidate_name: string
  skills: string[]
  experience_years: number | null
  education: string
  status: 'pending' | 'processing' | 'indexed' | 'failed'
}

export interface JdRequirements {
  required_skills: string[]
  min_experience_years: number | null
  jd_keywords_count: number
}

export interface MatchEntry {
  candidate_name: string
  resume_path: string
  match_score: number
  matched_skills: string[]
  relevant_excerpts: string[]
  reasoning: string
  experience_years?: number | null
  matched_sections?: string[]
}

export interface MatchResult {
  job_description: string
  top_matches: MatchEntry[]
}

export interface SearchHistoryEntry {
  id: string
  title: string
  timestamp: string
  matchCount: number
}
