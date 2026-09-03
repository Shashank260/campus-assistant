import { useState, useEffect, useRef } from 'react'
import { useApp } from '../../context/AppContext.jsx'
import { ingestPDF, ingestImage, getDocCount } from '../../api.js'

function UploadZone({ accept, icon, label, hint, onFile, loading }) {
  const inputRef = useRef(null)

  function handleDrop(e) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) onFile(file)
  }

  return (
    <div
      className="upload-zone"
      onClick={() => !loading && inputRef.current?.click()}
      onDragOver={e => e.preventDefault()}
      onDrop={handleDrop}
      style={loading ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={e => { 
          const f = e.target.files[0]; 
          if (f) {
            onFile(f);
          }
        }}
      />
      {loading
        ? <i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
        : <i className={`ti ${icon}`} aria-hidden="true" />
      }
      {loading ? 'Uploading…' : label}
      <span>{hint}</span>
    </div>
  )
}

function UploadResult({ result, onDismiss }) {
  if (!result) return null
  return (
    <div style={{
      background: 'var(--bg-surface2)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '10px 12px',
      fontSize: 12,
      color: 'var(--text-secondary)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8,
      marginTop: 10,
    }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <i className="ti ti-check" style={{ color: '#1D9E75', fontSize: 14 }} aria-hidden="true" />
        <strong style={{ color: 'var(--text-primary)' }}>{result.file}</strong>
        &nbsp;— {result.chunks_added} chunks added
        {result.extracted_chars && ` · ${result.extracted_chars} chars extracted`}
      </span>
      <button
        onClick={onDismiss}
        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14 }}
        aria-label="Dismiss"
      >
        <i className="ti ti-x" aria-hidden="true" />
      </button>
    </div>
  )
}

export default function KBPanel() {
  const { userId, showToast } = useApp()

  const [pdfTitle,     setPdfTitle]     = useState('')
  const [imageTitle,   setImageTitle]   = useState('')
  const [pdfLoading,   setPdfLoading]   = useState(false)
  const [imageLoading, setImageLoading] = useState(false)
  const [pdfResult,    setPdfResult]    = useState(null)
  const [imageResult,  setImageResult]  = useState(null)
  const [docCount,     setDocCount]     = useState(null)
  const [countLoading, setCountLoading] = useState(false)

  useEffect(() => {
    fetchDocCount()
  }, [userId])

  async function fetchDocCount() {
    if (!userId) return
    setCountLoading(true)
    try {
      const data = await getDocCount(userId)
      setDocCount(data)
    } catch {
      // silently fail — not critical
    } finally {
      setCountLoading(false)
    }
  }

  async function handlePDF(file) {
    if (!userId) { showToast('No user ID — check Settings ⚙️'); return }
    setPdfLoading(true)
    setPdfResult(null)
    try {
      const data = await ingestPDF({ userId, docTitle: pdfTitle, file })
      setPdfResult(data)
      setPdfTitle('')
      showToast(`PDF ingested — ${data.chunks_added} chunks added`)
      fetchDocCount()
    } catch (e) {
      showToast(`Upload failed: ${e.message}`)
    } finally {
      setPdfLoading(false)
    }
  }

  async function handleImage(file) {
    if (!userId) { showToast('No user ID — check Settings ⚙️'); return }
    setImageLoading(true)
    setImageResult(null)
    try {
      const data = await ingestImage({ userId, docTitle: imageTitle, file })
      setImageResult(data)
      setImageTitle('')
      showToast(`Image ingested — ${data.chunks_added} chunks added`)
      fetchDocCount()
    } catch (e) {
      showToast(`Upload failed: ${e.message}`)
    } finally {
      setImageLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      <div className="topbar">
        <span className="topbar-title">Knowledge base</span>
      </div>

      <div className="panel-inner">

        {/* ── PDF ── */}
        <div className="section-card">
          <h3>
            <i className="ti ti-file-type-pdf" aria-hidden="true" />
            Upload PDF
          </h3>

          <UploadZone
            accept=".pdf,application/pdf"
            icon="ti-cloud-upload"
            label="Click to upload or drag a PDF here"
            hint="Saved permanently to your knowledge base"
            onFile={handlePDF}
            loading={pdfLoading}
          />

          <div style={{ marginTop: 12 }}>
            <div className="form-group">
              <label className="form-label">Document title (optional)</label>
              <input
                className="form-input"
                type="text"
                placeholder="e.g. Biology Textbook Chapter 3"
                value={pdfTitle}
                onChange={e => setPdfTitle(e.target.value)}
                disabled={pdfLoading}
              />
            </div>
          </div>

          <UploadResult result={pdfResult} onDismiss={() => setPdfResult(null)} />
        </div>

        {/* ── IMAGE ── */}
        <div className="section-card">
          <h3>
            <i className="ti ti-photo" aria-hidden="true" />
            Upload Image
          </h3>

          <UploadZone
            accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff"
            icon="ti-cloud-upload"
            label="Click to upload an image"
            hint="OCR extracts text and adds it to your knowledge base · jpg, png, webp, bmp, tiff"
            onFile={handleImage}
            loading={imageLoading}
          />

          <div style={{ marginTop: 12 }}>
            <div className="form-group">
              <label className="form-label">Document title (optional)</label>
              <input
                className="form-input"
                type="text"
                placeholder="e.g. Lecture Slide 7"
                value={imageTitle}
                onChange={e => setImageTitle(e.target.value)}
                disabled={imageLoading}
              />
            </div>
          </div>

          <UploadResult result={imageResult} onDismiss={() => setImageResult(null)} />
        </div>

        {/* ── COLLECTION ── */}
        <div className="section-card">
          <h3>
            <i className="ti ti-database" aria-hidden="true" />
            Your collection
          </h3>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            {countLoading
              ? <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading…</span>
              : docCount
                ? (
                  <div className="doc-count-pill">
                    <i className="ti ti-files" style={{ fontSize: 14 }} aria-hidden="true" />
                    <strong>{docCount.doc_count}</strong> documents indexed
                  </div>
                )
                : (
                  <div className="doc-count-pill">
                    <i className="ti ti-files" style={{ fontSize: 14 }} aria-hidden="true" />
                    <strong>0</strong> documents indexed
                  </div>
                )
            }
            <button
              className="btn btn-secondary btn-sm"
              onClick={fetchDocCount}
              disabled={countLoading}
            >
              <i className="ti ti-refresh" style={{ fontSize: 13 }} aria-hidden="true" />
              Refresh
            </button>
          </div>

          {docCount && (
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
              Collection: <span style={{ fontFamily: 'DM Mono, monospace' }}>{docCount.collection}</span>
            </p>
          )}
        </div>

      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}