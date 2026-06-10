import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { MatchResult, SearchHistoryEntry } from '../types'

interface AppContextValue {
  matchResult: MatchResult | null
  setMatchResult: (result: MatchResult | null) => void
  searchHistory: SearchHistoryEntry[]
  addSearchHistory: (entry: SearchHistoryEntry) => void
  jobTitle: string
  setJobTitle: (title: string) => void
}

const AppContext = createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [matchResult, setMatchResult] = useState<MatchResult | null>(null)
  const [searchHistory, setSearchHistory] = useState<SearchHistoryEntry[]>([])
  const [jobTitle, setJobTitle] = useState('Job Match')

  const addSearchHistory = useCallback((entry: SearchHistoryEntry) => {
    setSearchHistory((current) => [entry, ...current].slice(0, 5))
  }, [])

  const value = useMemo(
    () => ({
      matchResult,
      setMatchResult,
      searchHistory,
      addSearchHistory,
      jobTitle,
      setJobTitle,
    }),
    [matchResult, searchHistory, addSearchHistory, jobTitle],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error('useApp must be used within AppProvider')
  }
  return context
}
