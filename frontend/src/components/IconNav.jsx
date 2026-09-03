import { useNavigate, useLocation } from 'react-router-dom'

export default function IconNav({ onSettingsClick }) {
  const navigate  = useNavigate()
  const location  = useLocation()
  const path      = location.pathname

  const navItems = [
    { icon: 'ti-message-2',     route: '/',        label: 'Chat'           },
    { icon: 'ti-books',         route: '/kb',       label: 'Knowledge base' },
    { icon: 'ti-brand-youtube', route: '/youtube',  label: 'YouTube'        },
  ]

  return (
    <nav className="icon-nav">
      <div className="nav-logo">C</div>

      {navItems.map(({ icon, route, label }) => (
        <button
          key={route}
          className={`nav-btn ${path === route ? 'active' : ''}`}
          onClick={() => navigate(route)}
          aria-label={label}
        >
          <i className={`ti ${icon}`} aria-hidden="true" />
          <span className="nav-tooltip">{label}</span>
        </button>
      ))}

      <div className="nav-spacer" />

      <button
        className="nav-btn"
        onClick={onSettingsClick}
        aria-label="Settings"
      >
        <i className="ti ti-settings" aria-hidden="true" />
        <span className="nav-tooltip">Settings</span>
      </button>
    </nav>
  )
}