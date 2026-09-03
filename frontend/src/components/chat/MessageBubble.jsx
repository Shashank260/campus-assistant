import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useApp } from '../../context/AppContext.jsx'
import { pushToNotion } from '../../api.js'

export default function MessageBubble({ msg, userId }) {
  const { showToast, notionConnected, activeConvId, activeConvTitle } = useApp()
  const [sourcesOpen,   setSourcesOpen]   = useState(false)
  const [notionLoading, setNotionLoading] = useState(false)

  // ── typing indicator ──────────────────────────────────────────────────────
  if (msg.loading) {
    return (
      <div className="msg ai">
        <div className="msg-avatar ai">C</div>
        <div className="msg-body">
          <div className="typing-indicator">
            <div className="typing-dot" />
            <div className="typing-dot" />
            <div className="typing-dot" />
          </div>
        </div>
      </div>
    )
  }

  // ── user message ──────────────────────────────────────────────────────────
  if (msg.role === 'user') {
    const initials = userId ? userId.slice(0, 2).toUpperCase() : 'U'
    return (
      <div className="msg user">
        <div className="msg-avatar user">{initials}</div>
        <div className="msg-body">
          {msg.image && (
            <img src={msg.image} alt="attachment" className="msg-image" />
          )}
          {msg.content && (
            <div className="msg-bubble">{msg.content}</div>
          )}
        </div>
      </div>
    )
  }

  // ── assistant message ─────────────────────────────────────────────────────
  const hasSources = msg.sources && msg.sources.length > 0

  // Convert common LaTeX symbols to Unicode so they render without a LaTeX engine
  function sanitizeLatex(text) {
    if (!text) return ''
    return text
      .replace(/\$\\rightarrow\$/g, '→')
      .replace(/\$\\leftarrow\$/g, '←')
      .replace(/\$\\leftrightarrow\$/g, '↔')
      .replace(/\$\\Rightarrow\$/g, '⇒')
      .replace(/\$\\Leftarrow\$/g, '⇐')
      .replace(/\$\\Leftrightarrow\$/g, '⇔')
      .replace(/\$\\times\$/g, '×')
      .replace(/\$\\div\$/g, '÷')
      .replace(/\$\\pm\$/g, '±')
      .replace(/\$\\neq\$/g, '≠')
      .replace(/\$\\leq\$/g, '≤')
      .replace(/\$\\geq\$/g, '≥')
      .replace(/\$\\approx\$/g, '≈')
      .replace(/\$\\infty\$/g, '∞')
      .replace(/\$\\alpha\$/g, 'α')
      .replace(/\$\\beta\$/g, 'β')
      .replace(/\$\\gamma\$/g, 'γ')
      .replace(/\$\\delta\$/g, 'δ')
      .replace(/\$\\sigma\$/g, 'σ')
      .replace(/\$\\mu\$/g, 'μ')
      .replace(/\$\\pi\$/g, 'π')
      .replace(/\$\\theta\$/g, 'θ')
      .replace(/\$\\lambda\$/g, 'λ')
      .replace(/\\rightarrow/g, '→')
      .replace(/\\leftarrow/g, '←')
      .replace(/\\Rightarrow/g, '⇒')
  }

  const renderedContent = sanitizeLatex(msg.content)

  async function handleNotionPush() {
    if (!notionConnected) {
      showToast('Connect Notion in Settings ⚙️ first')
      return
    }
    setNotionLoading(true)
    try {
      const data = await pushToNotion({
        userId,
        content:           msg.content,
        conversationId:    activeConvId,
        conversationTitle: activeConvTitle,
      })
      showToast(`Pushed to Notion ✓`)
    } catch {
      showToast('Notion push failed — check your connection in Settings')
    } finally {
      setNotionLoading(false)
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(msg.content || '')
      .then(() => showToast('Copied to clipboard'))
      .catch(() => showToast('Copy failed'))
  }

  return (
    <div className="msg ai">
      <div className="msg-avatar ai">C</div>
      <div className="msg-body">

        {/* bubble */}
        <div className={`msg-bubble ${msg.isError ? 'error-bubble' : ''}`}
          style={msg.isError ? { borderColor: 'rgba(226,75,74,0.3)', color: 'var(--text-secondary)' } : {}}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {renderedContent}
          </ReactMarkdown>
        </div>

        {/* actions */}
        <div className="msg-actions">
          <button
            className="msg-action-btn notion"
            onClick={handleNotionPush}
            disabled={notionLoading}
            title={notionConnected ? 'Push to Notion' : 'Connect Notion in Settings first'}
          >
            {notionLoading
              ? <i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite', fontSize: 12 }} />
              : <i className="ti ti-brand-notion" />
            }
            Push to Notion
          </button>

          <button className="msg-action-btn" onClick={handleCopy} title="Copy response">
            <i className="ti ti-copy" />
            Copy
          </button>

          {hasSources && (
            <button
              className="msg-action-btn"
              onClick={() => setSourcesOpen(o => !o)}
            >
              <i className="ti ti-file-text" />
              {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
            </button>
          )}
        </div>

        {/* sources */}
        {hasSources && sourcesOpen && (
          <div className="sources-block">
            <div
              className={`sources-toggle ${sourcesOpen ? 'open' : ''}`}
              onClick={() => setSourcesOpen(o => !o)}
            >
              <i className="ti ti-chevron-down" aria-hidden="true" />
              <span>Sources used</span>
            </div>
            <div className="sources-list">
              {msg.sources.map((src, i) => (
                <div className="source-item" key={i}>
                  <i
                    className={`ti ${src.source_type === 'pdf' ? 'ti-file-type-pdf' : 'ti-photo'}`}
                    style={{ fontSize: 13, color: 'var(--coral)' }}
                    aria-hidden="true"
                  />
                  <span className="source-label">{src.doc_title}</span>
                  {src.page && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>p.{src.page}</span>
                  )}
                  <span className="source-type">{src.source_type}</span>
                  <span className="source-score">{src.score?.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* model used — subtle footer */}
        {msg.model && (
          <span style={{ fontSize: 10, color: 'var(--text-muted)', paddingLeft: 2 }}>
            {msg.model}
          </span>
        )}

      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}