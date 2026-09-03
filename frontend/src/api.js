const BASE = '/api'

// ─── helper ───────────────────────────────────────────────────────────────────

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

function authHeaders(apiKey) {
  return { 'Content-Type': 'application/json', 'x-api-key': apiKey }
}

// ─── health ───────────────────────────────────────────────────────────────────

export async function checkHealth() {
  return request('/health')
}

// ─── conversations ────────────────────────────────────────────────────────────

export async function createConversation(userId) {
  return request('/conversations/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  })
}

export async function listConversations(userId) {
  return request(`/conversations/${userId}`)
}

export async function getConversationHistory(conversationId) {
  return request(`/conversations/${conversationId}/history`)
}

export async function deleteConversation(conversationId) {
  return request(`/conversations/${conversationId}`, { method: 'DELETE' })
}

// ─── chat ─────────────────────────────────────────────────────────────────────

export async function sendChat({ userId, message, conversationId, fastMode, apiKey }) {
  return request('/chat', {
    method: 'POST',
    headers: authHeaders(apiKey),
    body: JSON.stringify({
      user_id: userId,
      message,
      conversation_id: conversationId,
      fast_mode: fastMode,
      api_key: apiKey,
    }),
  })
}

// ─── context (ephemeral image in chat) ────────────────────────────────────────

export async function sendImageContext({ userId, question, conversationId, apiKey, file }) {
  const form = new FormData()
  form.append('user_id', userId)
  form.append('api_key', apiKey)
  if (question) form.append('question', question)
  if (conversationId) form.append('conversation_id', conversationId)
  form.append('file', file)

  const res = await fetch(`${BASE}/context/image`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Image context failed')
  }
  return res.json()
}

// ─── ingestion ────────────────────────────────────────────────────────────────

export async function ingestPDF({ userId, docTitle, file }) {
  const form = new FormData()
  form.append('user_id', userId)
  if (docTitle) form.append('doc_title', docTitle)
  form.append('doc_type', 'pdf')
  form.append('file', file)

  try {
    const res = await fetch(`${BASE}/ingest/pdf`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'PDF ingestion failed')
    }
    return await res.json()
  } catch (error) {
    throw new Error(error.message || 'Network connection lost during vector upload processing')
  }
}

export async function ingestImage({ userId, docTitle, file }) {
  const form = new FormData()
  form.append('user_id', userId)
  if (docTitle) form.append('doc_title', docTitle)
  form.append('file', file)

  const res = await fetch(`${BASE}/ingest/image`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Image ingestion failed')
  }
  return res.json()
}

export async function getDocCount(userId) {
  return request(`/my/docs/${userId}`)
}

// ─── youtube ──────────────────────────────────────────────────────────────────

export async function getYoutubeLanguages(url) {
  return request(`/tools/youtube/languages?url=${encodeURIComponent(url)}`)
}

export async function processYoutube({
  url,
  languageCode,
  promptStyle,
  customPrompt,
  outputLanguage,
  conversationId,
  userId,
  apiKey,
}) {
  return request('/tools/youtube', {
    method: 'POST',
    headers: authHeaders(apiKey),
    body: JSON.stringify({
      url,
      language_code: languageCode,
      prompt_style: promptStyle,
      custom_prompt: customPrompt || '',
      output_language: outputLanguage,
      conversation_id: conversationId || '',
      user_id: userId || '',
      api_key: apiKey,
    }),
  })
}

// ─── notion ───────────────────────────────────────────────────────────────────

export async function setupNotion({ userId, notionKey, notionPageId }) {
  return request('/notion/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      notion_key: notionKey,
      notion_page_id: notionPageId,
    }),
  })
}

export async function getNotionStatus(userId) {
  return request(`/notion/status/${userId}`)
}

export async function pushToNotion({ userId, content, conversationId, conversationTitle }) {
  return request('/notion/push', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      content,
      conversation_id: conversationId || '',
      conversation_title: conversationTitle || '',
    }),
  })
}