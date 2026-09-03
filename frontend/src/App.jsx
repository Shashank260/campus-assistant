import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppProvider } from './context/AppContext.jsx'
import IconNav from './components/IconNav.jsx'
import Sidebar from './components/Sidebar.jsx'
import ChatPanel from './components/chat/ChatPanel.jsx'
import KBPanel from './components/kb/KBPanel.jsx'
import YoutubePanel from './components/youtube/YoutubePanel.jsx'
import Settings from './components/Settings.jsx'
import Login from './components/Login.jsx'

export default function App() {
  const [authed, setAuthed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />
  }

  return (
    <AppProvider>
      <BrowserRouter>
        <div className="app-shell">
          <IconNav onSettingsClick={() => setSettingsOpen(true)} />

          <Routes>
            <Route
              path="/"
              element={
                <>
                  <Sidebar />
                  <main className="main-panel">
                    <ChatPanel />
                  </main>
                </>
              }
            />
            <Route
              path="/kb"
              element={
                <main className="main-panel">
                  <KBPanel />
                </main>
              }
            />
            <Route
              path="/youtube"
              element={
                <main className="main-panel">
                  <YoutubePanel />
                </main>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          {settingsOpen && (
            <Settings onClose={() => setSettingsOpen(false)} />
          )}
        </div>
      </BrowserRouter>
    </AppProvider>
  )
}