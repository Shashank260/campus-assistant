import { useState, useEffect, useRef } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { setupNotion, getNotionStatus } from '../api.js'

export default function Settings({ onClose }) {
  const {
    userId, apiKey,
    notionKey, notionPageId, notionConnected,
    setNotionConnected,
    saveSettings,
    showToast,
  } = useApp()

  const [localUserId,     setLocalUserId]     = useState(userId)
  const [localApiKey,     setLocalApiKey]      = useState(apiKey)
  const [localNotionKey,  setLocalNotionKey]   = useState(notionKey)
  const [localNotionPage, setLocalNotionPage]  = useState(notionPageId)
  const [notionLoading,   setNotionLoading]    = useState(false)
  const [notionStatus,    setNotionStatus]     = useState(null)

  const backdropRef = useRef(null)

  // check notion status on open
  useEffect(() => {
    if (!userId) return
    getNotionStatus(userId)
      .then(data => {
        setNotionConnected(data.connected)
        setNotionStatus(data)
      })
      .catch(() => {})
  }, [userId, setNotionConnected])

  function handleBackdrop(e) {
    if (e.target === backdropRef.current) onClose()
  }

  function handleSave() {
    saveSettings({
      userId:      localUserId.trim(),
      apiKey:      localApiKey.trim(),
      notionKey:   localNotionKey.trim(),
      notionPageId: localNotionPage.trim(),
    })
    showToast('Settings saved')
    onClose()
  }

  async function handleConnectNotion() {
    if (!localNotionKey.trim() || !localNotionPage.trim()) {
      showToast('Enter both Notion key and page ID first')
      return
    }
    setNotionLoading(true)
    try {
      await setupNotion({
        userId,
        notionKey:   localNotionKey.trim(),
        notionPageId: localNotionPage.trim(),
      })
      saveSettings({
        notionKey:   localNotionKey.trim(),
        notionPageId: localNotionPage.trim(),
      })
      setNotionConnected(true)
      showToast('Notion connected ✓')
    } catch (e) {
      showToast('Notion connection failed — check your key and page ID')
    } finally {
      setNotionLoading(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      ref={backdropRef}
      onClick={handleBackdrop}
    >
      <div className="settings-modal">
        <h4>
          <i className="ti ti-settings" aria-hidden="true" />
          Settings
        </h4>

        {/* ── USER ── */}
        <div className="settings-row">
          <label className="settings-label">User ID</label>
          <input
            className="settings-input"
            type="text"
            value={localUserId}
            onChange={e => setLocalUserId(e.target.value)}
            placeholder="student123"
          />
        </div>

        <div className="settings-row">
          <label className="settings-label">Google AI Studio API key</label>
          <input
            className="settings-input"
            type="password"
            value={localApiKey}
            onChange={e => setLocalApiKey(e.target.value)}
            placeholder="AIza..."
          />
        </div>

        <div className="settings-divider" />

        {/* ── NOTION ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 5 }}>
            <i className="ti ti-brand-notion" style={{ fontSize: 14 }} aria-hidden="true" />
            Notion integration
          </span>
          {notionConnected
            ? <span className="badge success"><i className="ti ti-check" style={{ fontSize: 11 }} /> Connected</span>
            : <span className="badge muted">Not connected</span>
          }
        </div>

        <div className="settings-row">
          <label className="settings-label">Notion integration key</label>
          <input
            className="settings-input"
            type="password"
            value={localNotionKey}
            onChange={e => setLocalNotionKey(e.target.value)}
            placeholder="secret_xxxx"
          />
        </div>

        <div className="settings-row">
          <label className="settings-label">Master page ID or URL</label>
          <input
            className="settings-input"
            type="text"
            value={localNotionPage}
            onChange={e => setLocalNotionPage(e.target.value)}
            placeholder="https://notion.so/..."
          />
        </div>

        <button
          className="btn btn-secondary btn-sm"
          onClick={handleConnectNotion}
          disabled={notionLoading}
          style={{ width: '100%', justifyContent: 'center', marginBottom: 4 }}
        >
          {notionLoading
            ? <><i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} /> Connecting…</>
            : <><i className="ti ti-plug" /> {notionConnected ? 'Reconnect Notion' : 'Connect Notion'}</>
          }
        </button>

        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, lineHeight: 1.5 }}>
          Create an integration at{' '}
          <a href="https://notion.so/my-integrations" target="_blank" rel="noreferrer"
            style={{ color: 'var(--coral)', textDecoration: 'none' }}>
            notion.so/my-integrations
          </a>
          {' '}and share your master page with it.
        </p>

        <div className="settings-divider" />

        <div className="settings-footer">
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSave}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            Save
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onClose}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            Cancel
          </button>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}4