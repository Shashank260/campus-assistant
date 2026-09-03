import { createContext, useContext, useState, useCallback } from 'react'
import { createConversation, listConversations, deleteConversation } from '../api.js'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  // ─── user / auth ────────────────────────────────────────────────────────────
  const [userId, setUserId] = useState(() => localStorage.getItem('userId') || '')
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('apiKey') || '')

  // ─── notion ─────────────────────────────────────────────────────────────────
  const [notionKey, setNotionKey] = useState(() => localStorage.getItem('notionKey') || '')
  const [notionPageId, setNotionPageId] = useState(() => localStorage.getItem('notionPageId') || '')
  const [notionConnected, setNotionConnected] = useState(false)

  // ─── conversations ───────────────────────────────────────────────────────────
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId] = useState('')
  const [activeConvTitle, setActiveConvTitle] = useState('New conversation')

  // ─── messages (current conversation) ────────────────────────────────────────
  const [messages, setMessages] = useState([])

  // ─── ui ─────────────────────────────────────────────────────────────────────
  const [fastMode, setFastMode] = useState(false)
  const [toast, setToast] = useState({ visible: false, message: '' })

  // ─── persist settings ────────────────────────────────────────────────────────
  const saveSettings = useCallback(({ userId: uid, apiKey: key, notionKey: nk, notionPageId: npid }) => {
    if (uid !== undefined) { setUserId(uid); localStorage.setItem('userId', uid) }
    if (key !== undefined) { setApiKey(key); localStorage.setItem('apiKey', key) }
    if (nk !== undefined) { setNotionKey(nk); localStorage.setItem('notionKey', nk) }
    if (npid !== undefined) { setNotionPageId(npid); localStorage.setItem('notionPageId', npid) }
  }, [])

  // ─── toast ───────────────────────────────────────────────────────────────────
  const showToast = useCallback((message, duration = 2200) => {
    setToast({ visible: true, message })
    setTimeout(() => setToast({ visible: false, message: '' }), duration)
  }, [])

  // ─── conversation actions ────────────────────────────────────────────────────
  const loadConversations = useCallback(async () => {
    if (!userId) return
    try {
      const data = await listConversations(userId)
      const list = data.conversations || []
      setConversations(list)

      // Keep active conversation title in sync with backend updates
      if (activeConvId) {
        const active = list.find(c => c.conversation_id === activeConvId)
        if (active && active.title) {
          setActiveConvTitle(active.title)
        }
      }
    } catch (e) {
      console.error('Failed to load conversations:', e)
    }
  }, [userId, activeConvId])

  const startNewConversation = useCallback(async () => {
    if (!userId) return
    try {
      const data = await createConversation(userId)
      setActiveConvId(data.conversation_id)
      setActiveConvTitle('New conversation')
      setMessages([])
      await loadConversations()
      return data.conversation_id
    } catch (e) {
      showToast('Could not create conversation')
      console.error(e)
    }
  }, [userId, loadConversations, showToast])

  const removeConversation = useCallback(async (convId) => {
    try {
      await deleteConversation(convId)
      if (convId === activeConvId) {
        setActiveConvId('')
        setActiveConvTitle('New conversation')
        setMessages([])
      }
      await loadConversations()
      showToast('Conversation deleted')
    } catch (e) {
      showToast('Could not delete conversation')
      console.error(e)
    }
  }, [activeConvId, loadConversations, showToast])

  const selectConversation = useCallback((conv) => {
    setActiveConvId(conv.conversation_id)
    setActiveConvTitle(conv.title || 'Conversation')
    setMessages([])
  }, [])

  // ─── message helpers ─────────────────────────────────────────────────────────
  const appendMessage = useCallback((msg) => {
    setMessages(prev => [...prev, msg])
  }, [])

  const updateLastMessage = useCallback((updater) => {
    setMessages(prev => {
      const copy = [...prev]
      copy[copy.length - 1] = updater(copy[copy.length - 1])
      return copy
    })
  }, [])

  return (
    <AppContext.Provider value={{
      // user
      userId, apiKey,
      // notion
      notionKey, notionPageId, notionConnected, setNotionConnected,
      // settings
      saveSettings,
      // conversations
      conversations, activeConvId, activeConvTitle,
      loadConversations, startNewConversation, removeConversation, selectConversation,
      // messages
      messages, setMessages, appendMessage, updateLastMessage,
      // ui
      fastMode, setFastMode,
      toast, showToast,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}