import { useState } from 'react'
import { useApp } from '../../context/AppContext.jsx'
import { getYoutubeLanguages, processYoutube } from '../../api.js'

const STYLE_OPTIONS = [
  { value: 'bullet_summary', label: 'Bullet summary',       desc: 'Concise bullet points' },
  { value: 'detailed',       label: 'Detailed paragraphs',  desc: 'Full paragraph breakdown' },
  { value: 'eli5',           label: "Explain like I'm 12",  desc: 'Simple, plain language' },
  { value: 'raw',            label: 'Raw transcript',        desc: 'No LLM — fastest' },
  { value: 'custom',         label: 'Custom prompt',         desc: 'Write your own instruction' },
]

export default function YoutubePanel() {
  const { userId, apiKey, activeConvId, showToast } = useApp()

  const [url,            setUrl]            = useState('')
  const [languages,      setLanguages]      = useState([])
  const [langLoading,    setLangLoading]    = useState(false)
  const [selectedLang,   setSelectedLang]   = useState('en')
  const [style,          setStyle]          = useState('bullet_summary')
  const [customPrompt,   setCustomPrompt]   = useState('')
  const [outputLang,     setOutputLang]     = useState('English')
  const [saveToChat,     setSaveToChat]     = useState(false)
  const [processing,     setProcessing]     = useState(false)
  const [result,         setResult]         = useState(null)
  const [step,           setStep]           = useState(1) // 1 = url, 2 = options, 3 = result

  async function handleCheckLanguages() {
    if (!url.trim()) { showToast('Enter a YouTube URL first'); return }
    setLangLoading(true)
    setLanguages([])
    setResult(null)
    setStep(1)
    try {
      const data = await getYoutubeLanguages(url.trim())
      setLanguages(data.languages || [])
      setStep(2)
      if (data.languages?.length) {
        setSelectedLang(data.languages[0].code)
      }
    } catch (e) {
      showToast(`Could not fetch languages: ${e.message}`)
    } finally {
      setLangLoading(false)
    }
  }

  async function handleProcess() {
    if (!apiKey && style !== 'raw') {
      showToast('Add your API key in Settings ⚙️')
      return
    }
    setProcessing(true)
    setResult(null)
    try {
      const data = await processYoutube({
        url:            url.trim(),
        languageCode:   selectedLang,
        promptStyle:    style,
        customPrompt:   style === 'custom' ? customPrompt : '',
        outputLanguage: outputLang,
        conversationId: saveToChat ? activeConvId : '',
        userId:         saveToChat ? userId : '',
        apiKey,
      })
      setResult(data)
      setStep(3)
    } catch (e) {
      showToast(`Processing failed: ${e.message}`)
    } finally {
      setProcessing(false)
    }
  }

  function handleCopy() {
    if (!result) return
    navigator.clipboard.writeText(result.processed_text)
      .then(() => showToast('Copied to clipboard'))
      .catch(() => showToast('Copy failed'))
  }

  function handleReset() {
    setUrl('')
    setLanguages([])
    setResult(null)
    setStep(1)
    setStyle('bullet_summary')
    setCustomPrompt('')
    setOutputLang('English')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      <div className="topbar">
        <span className="topbar-title">YouTube transcript</span>
        {step > 1 && (
          <div className="topbar-actions">
            <button className="icon-btn" onClick={handleReset} title="Start over" aria-label="Reset">
              <i className="ti ti-refresh" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      <div className="panel-inner">

        {/* ── STEP 1: URL ── */}
        <div className="section-card">
          <h3>
            <i className="ti ti-link" aria-hidden="true" />
            Step 1 — Video URL
          </h3>

          <div className="form-group">
            <label className="form-label">YouTube URL</label>
            <input
              className="form-input"
              type="url"
              placeholder="https://youtube.com/watch?v=..."
              value={url}
              onChange={e => { setUrl(e.target.value); setStep(1); setLanguages([]); setResult(null) }}
              disabled={langLoading}
            />
          </div>

          <div style={{ marginTop: 12 }}>
            <button
              className="btn btn-primary"
              onClick={handleCheckLanguages}
              disabled={langLoading || !url.trim()}
            >
              {langLoading
                ? <><i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} /> Checking…</>
                : <><i className="ti ti-language" /> Check available languages</>
              }
            </button>
          </div>
        </div>

        {/* ── STEP 2: OPTIONS ── */}
        {step >= 2 && (
          <div className="section-card">
            <h3>
              <i className="ti ti-adjustments" aria-hidden="true" />
              Step 2 — Options
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

              {/* language */}
              <div className="form-group">
                <label className="form-label">Transcript language</label>
                <select
                  className="form-select"
                  value={selectedLang}
                  onChange={e => setSelectedLang(e.target.value)}
                >
                  {languages.map(l => (
                    <option key={l.code} value={l.code}>
                      {l.name}{l.auto_generated ? ' (auto-generated)' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* style */}
              <div className="form-group">
                <label className="form-label">Processing style</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {STYLE_OPTIONS.map(opt => (
                    <label
                      key={opt.value}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        padding: '8px 12px',
                        borderRadius: 8,
                        border: `1px solid ${style === opt.value ? 'var(--coral-border)' : 'var(--border)'}`,
                        background: style === opt.value ? 'var(--coral-muted)' : 'var(--bg-surface2)',
                        cursor: 'pointer',
                        transition: 'all 0.12s',
                      }}
                    >
                      <input
                        type="radio"
                        name="style"
                        value={opt.value}
                        checked={style === opt.value}
                        onChange={() => setStyle(opt.value)}
                        style={{ accentColor: 'var(--coral)' }}
                      />
                      <span>
                        <span style={{ fontSize: 13, color: 'var(--text-primary)', display: 'block' }}>
                          {opt.label}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {opt.desc}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* custom prompt */}
              {style === 'custom' && (
                <div className="form-group">
                  <label className="form-label">Custom prompt</label>
                  <textarea
                    className="form-input"
                    rows={3}
                    placeholder="e.g. Extract all dates and events mentioned…"
                    value={customPrompt}
                    onChange={e => setCustomPrompt(e.target.value)}
                    style={{ resize: 'vertical', minHeight: 72 }}
                  />
                </div>
              )}

              {/* output language */}
              <div className="form-group">
                <label className="form-label">Output language</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="English"
                  value={outputLang}
                  onChange={e => setOutputLang(e.target.value)}
                />
              </div>

              {/* save to chat memory */}
              <label style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={saveToChat}
                  onChange={e => setSaveToChat(e.target.checked)}
                  style={{ accentColor: 'var(--coral)', width: 14, height: 14 }}
                />
                Save result to current chat memory
              </label>

              <button
                className="btn btn-primary"
                onClick={handleProcess}
                disabled={processing}
                style={{ alignSelf: 'flex-start' }}
              >
                {processing
                  ? <><i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} /> Processing…</>
                  : <><i className="ti ti-player-play" /> Process transcript</>
                }
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 3: RESULT ── */}
        {step === 3 && result && (
          <div className="section-card">
            <h3>
              <i className="ti ti-text-wrap" aria-hidden="true" />
              Result
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                {result.detected_language && (
                  <span className="badge muted">{result.detected_language}</span>
                )}
                <span className="badge muted">{result.prompt_style}</span>
              </span>
            </h3>

            <div className="yt-result">{result.processed_text}</div>

            <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary btn-sm" onClick={handleCopy}>
                <i className="ti ti-copy" style={{ fontSize: 13 }} aria-hidden="true" />
                Copy
              </button>
              {result.raw_transcript && style !== 'raw' && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    navigator.clipboard.writeText(result.raw_transcript)
                    showToast('Raw transcript copied')
                  }}
                >
                  <i className="ti ti-file-text" style={{ fontSize: 13 }} aria-hidden="true" />
                  Copy raw transcript
                </button>
              )}
            </div>
          </div>
        )}

      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}