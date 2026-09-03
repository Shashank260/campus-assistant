import { useState } from 'react'

export default function Login({ onLogin }) {
  const [userId, setUserId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (!userId.trim())  return setError('Please enter a user ID.')
    if (!apiKey.trim())  return setError('Please enter your Google AI Studio API key.')

    setLoading(true)
    try {
      const res = await fetch('/api/health')
      if (!res.ok) throw new Error('Backend unreachable')

      localStorage.setItem('userId', userId.trim())
      localStorage.setItem('apiKey', apiKey.trim())
      onLogin()
    } catch {
      setError('Cannot reach the backend. Make sure uvicorn is running on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-logo">C</div>

        <div>
          <h2>Campus Assistant</h2>
          <p>Your personal AI study companion — powered by your own notes.</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        <div className="form-group">
          <label className="form-label">User ID</label>
          <input
            className="form-input"
            type="text"
            placeholder="e.g. student123 or your email"
            value={userId}
            onChange={e => setUserId(e.target.value)}
            autoFocus
          />
        </div>

        <div className="form-group">
          <label className="form-label">Google AI Studio API key</label>
          <input
            className="form-input"
            type="password"
            placeholder="AIza..."
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            Get a free key at{' '}
            <a
              href="https://aistudio.google.com"
              target="_blank"
              rel="noreferrer"
              style={{ color: 'var(--coral)', textDecoration: 'none' }}
            >
              aistudio.google.com
            </a>
          </span>
        </div>

        <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%', justifyContent: 'center' }}>
          {loading
            ? <><i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} /> Connecting…</>
            : <><i className="ti ti-arrow-right" /> Enter</>
          }
        </button>

        <p style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: -8 }}>
          Authentication coming soon. Your key is stored locally only.
        </p>
      </form>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}