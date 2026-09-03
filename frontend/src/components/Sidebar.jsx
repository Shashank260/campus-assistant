import { useEffect } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { getConversationHistory } from '../api.js'

function groupByDate(conversations) {
  const today     = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  const fmt = (d) => d.toDateString()

  const groups = { Today: [], Yesterday: [], Earlier: [] }

  conversations.forEach(conv => {
    const d = new Date(conv.last_active)
    if (fmt(d) === fmt(today))          groups.Today.push(conv)
    else if (fmt(d) === fmt(yesterday)) groups.Yesterday.push(conv)
    else                                groups.Earlier.push(conv)
  })

  return groups
}

export default function Sidebar() {
  const {
    userId,
    conversations,
    activeConvId,
    loadConversations,
    startNewConversation,
    removeConversation,
    selectConversation,
    setMessages,
    appendMessage,
    showToast,
    apiKey,
  } = useApp()

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  async function handleSelect(conv) {
    if (conv.conversation_id === activeConvId) return
    selectConversation(conv)

    try {
      const data = await getConversationHistory(conv.conversation_id)
      const msgs = (data.messages || []).map(m => ({
        role:    m.role,
        content: m.content,
        sources: [],
      }))
      setMessages(msgs)
    } catch {
      showToast('Could not load conversation history')
    }
  }

  async function handleNew() {
    await startNewConversation()
  }

  async function handleDelete(e, convId) {
    e.stopPropagation()
    await removeConversation(convId)
  }

  const groups  = groupByDate(conversations)
  const initials = userId
    ? userId.slice(0, 2).toUpperCase()
    : '??'

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">Conversations</span>
        <button
          className="sidebar-new-btn"
          onClick={handleNew}
          aria-label="New conversation"
        >
          <i className="ti ti-plus" aria-hidden="true" />
        </button>
      </div>

      <div className="sidebar-conversations">
        {conversations.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)', padding: '12px 6px' }}>
            No conversations yet. Hit + to start one.
          </p>
        )}

        {Object.entries(groups).map(([label, convs]) =>
          convs.length === 0 ? null : (
            <div key={label}>
              <div className="sidebar-section-label">{label}</div>
              {convs.map(conv => (
                <div
                  key={conv.conversation_id}
                  className={`conv-item ${conv.conversation_id === activeConvId ? 'active' : ''}`}
                  onClick={() => handleSelect(conv)}
                >
                  <i className="ti ti-message-2 conv-icon" aria-hidden="true" />
                  <span className="conv-text">
                    {conv.title || 'New conversation'}
                  </span>
                  <button
                    className="conv-del"
                    onClick={(e) => handleDelete(e, conv.conversation_id)}
                    aria-label="Delete conversation"
                  >
                    <i className="ti ti-trash" style={{ fontSize: 12 }} />
                  </button>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      <div className="sidebar-footer">
        <div className="user-pill">
          <div className="avatar">{initials}</div>
          <span className="user-name">{userId}</span>
        </div>
      </div>
    </aside>
  )
}