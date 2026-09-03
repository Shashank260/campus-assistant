import { useState, useEffect, useRef } from 'react'
import { useApp } from '../../context/AppContext.jsx'
import { sendChat, sendImageContext } from '../../api.js'
import MessageBubble from './MessageBubble.jsx'

export default function ChatPanel() {
  const {
    userId, apiKey,
    activeConvId, activeConvTitle,
    startNewConversation,
    loadConversations,
    messages, appendMessage, setMessages,
    fastMode, setFastMode,
    showToast,
  } = useApp()

  const [input,        setInput]        = useState('')
  const [loading,      setLoading]      = useState(false)
  const [attachedFile, setAttachedFile] = useState(null)
  const [previewUrl,   setPreviewUrl]   = useState(null)

  const messagesEndRef = useRef(null)
  const textareaRef    = useRef(null)
  const fileInputRef   = useRef(null)

  // scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])




  function handleFileSelect(e) {
    const file = e.target.files[0]
    if (!file) return
    setAttachedFile(file)
    setPreviewUrl(URL.createObjectURL(file))
    e.target.value = ''
  }

  function removeAttachment() {
    setAttachedFile(null)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
  }

  function autoGrow(el) {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleSend() {
    const text = input.trim()
    if ((!text && !attachedFile) || loading) return
    if (!apiKey) { showToast('Add your API key in Settings ⚙️'); return }

    // Lazily create a conversation on first send if none is active
    let convId = activeConvId
    if (!convId) {
      try {
        convId = await startNewConversation()
        if (!convId) { showToast('Could not start conversation'); return }
      } catch {
        showToast('Could not start conversation'); return
      }
    }

    const isFirstMessage = messages.length === 0

    // append user message
    appendMessage({
      role:    'user',
      content: text || '',
      image:   previewUrl,
    })

    const currentFile = attachedFile
    setInput('')
    setAttachedFile(null)
    setPreviewUrl(null)
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    // append typing indicator
    appendMessage({ role: 'assistant', content: null, loading: true })
    setLoading(true)

    try {
      let data

      if (currentFile) {
        // image context endpoint
        data = await sendImageContext({
          userId,
          question:       text || undefined,
          conversationId: convId,
          apiKey,
          file:           currentFile,
        })
        // normalise response shape
        data = { response: data.response, sources: [] }
      } else {
        data = await sendChat({
          userId,
          message:        text,
          conversationId: convId,
          fastMode,
          apiKey,
        })
      }

      // replace typing indicator with real response
      setMessages(prev => {
        const copy = [...prev]
        copy[copy.length - 1] = {
          role:    'assistant',
          content: data.response,
          sources: data.sources || [],
          model:   data.model_used,
        }
        return copy
      })

      if (isFirstMessage) {
        // Trigger sidebar reload to automatically show the new name!
        await loadConversations()
      }
    } catch (err) {
      setMessages(prev => {
        const copy = [...prev]
        copy[copy.length - 1] = {
          role:    'assistant',
          content: `Sorry, something went wrong: ${err.message}`,
          sources: [],
          isError: true,
        }
        return copy
      })
    } finally {
      setLoading(false)
    }
  }

  const canSend = (input.trim() || attachedFile) && !loading

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* topbar */}
      <div className="topbar">
        <span className="topbar-title">{activeConvTitle}</span>
        <div className="topbar-actions">
          <button
            className="icon-btn"
            onClick={() => { setMessages([]); showToast('Chat cleared') }}
            aria-label="Clear chat"
            title="Clear chat"
          >
            <i className="ti ti-eraser" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* messages */}
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <i className="ti ti-message-2" aria-hidden="true" />
            <p>Ask anything from your notes</p>
            <small>Answers are grounded in your uploaded documents</small>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} userId={userId} />
        ))}

        <div ref={messagesEndRef} style={{ height: 20 }} />
      </div>

      {/* input */}
      <div className="input-area">
        <div className="input-box">

          {/* image preview */}
          {attachedFile && (
            <div className="input-preview">
              <div className="preview-thumb">
                {previewUrl
                  ? <img src={previewUrl} alt="attachment preview" />
                  : <i className="ti ti-photo" aria-hidden="true" />
                }
              </div>
              <span className="preview-name">{attachedFile.name}</span>
              <button className="preview-remove" onClick={removeAttachment} aria-label="Remove image">
                <i className="ti ti-x" aria-hidden="true" />
              </button>
            </div>
          )}

          <div className="input-row">
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder={attachedFile ? 'Ask about this image…' : 'Ask anything from your notes…'}
              value={input}
              onChange={e => { setInput(e.target.value); autoGrow(e.target) }}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={loading}
            />
            <div className="input-btns">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
              />
              <button
                className="attach-btn"
                onClick={() => fileInputRef.current?.click()}
                aria-label="Attach image"
                title="Attach image (ephemeral — not saved to knowledge base)"
                disabled={loading}
              >
                <i className="ti ti-paperclip" aria-hidden="true" />
              </button>
              <button
                className="send-btn"
                onClick={handleSend}
                disabled={!canSend}
                aria-label="Send"
              >
                {loading
                  ? <i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
                  : <i className="ti ti-arrow-up" aria-hidden="true" />
                }
              </button>
            </div>
          </div>

          {/* fast mode toggle */}
          <div
            className="fast-toggle-row"
            onClick={() => setFastMode(f => !f)}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && setFastMode(f => !f)}
            aria-label={`Fast mode ${fastMode ? 'on' : 'off'}`}
          >
            <div className={`toggle-switch ${fastMode ? 'on' : ''}`}>
              <div className="toggle-knob" />
            </div>
            <span className="fast-label">
              {fastMode ? 'Fast mode on' : 'Fast mode'}
            </span>
          </div>

        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}