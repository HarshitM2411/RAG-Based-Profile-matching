import { NavLink } from 'react-router-dom'
import { Icon } from './Icon'

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'dashboard' },
  { to: '/ingestion', label: 'Resume Ingestion', icon: 'upload_file' },
  { to: '/matching', label: 'Job Matching', icon: 'query_stats' },
  { to: '/results', label: 'Match Results', icon: 'leaderboard' },
]

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 z-50 flex h-full w-[260px] flex-col bg-primary-container py-6">
      <div className="mb-8 px-6">
        <h1 className="text-lg font-semibold text-on-primary">TalentMatch RAG</h1>
        <p className="text-xs text-on-primary-container">Enterprise Talent Acquisition</p>
      </div>

      <nav className="flex-1 space-y-1 px-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 border-l-4 px-4 py-3 transition-colors duration-200 ${
                isActive
                  ? 'border-secondary bg-on-primary-fixed-variant/20 text-on-primary'
                  : 'border-transparent text-on-primary-container/70 hover:bg-on-primary-fixed-variant/10 hover:text-on-primary'
              }`
            }
          >
            <Icon name={item.icon} />
            <span className="text-sm">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto border-t border-on-primary-fixed-variant/20 px-6 pt-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary-container text-on-secondary">
            <Icon name="account_circle" />
          </div>
          <div>
            <p className="text-sm font-medium text-on-primary">Alex Recruiter</p>
            <p className="text-xs text-on-primary-container">Admin Access</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
