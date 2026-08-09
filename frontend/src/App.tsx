import { useEffect } from 'react'

import { useAppStore } from './stores/useAppStore'
import { useAuthStore } from './stores/useAuthStore'
import { OrbContainer } from './components/Orb/OrbContainer'

import { RemoteControl } from './components/Panels/RemoteControl'
import { FaceUnlock } from './components/Panels/FaceUnlock'
import { ScreenPreview } from './components/Panels/ScreenPreview'
import { SafetyBanner } from './components/SafetyBanner'
import { ReplyBox } from './components/ReplyBox'
import { InputRow } from './components/InputRow'
import { Header } from './components/Layout/Header'
import { LeftSidebar } from './components/Layout/LeftSidebar'
import { RightSidebar } from './components/Layout/RightSidebar'
import { Footer } from './components/Layout/Footer'
import { useWebSocket } from './hooks/useWebSocket'

function App() {
  const { addActivity } = useAppStore()
  const { isAuthenticated } = useAuthStore()
  // Initialize WebSocket connection (hook runs its own effect)
  useWebSocket()

  useEffect(() => {
    if (useAppStore.getState().activities.some((a) => a.id.startsWith('init-'))) return;
    const now = new Date().toISOString()
    addActivity({ id: 'init-1', time: now, text: 'All systems nominal', type: 'success' })
    addActivity({ id: 'init-2', time: now, text: 'Command center online · Safety v1.0 active', type: 'info' })
    addActivity({ id: 'init-3', time: now, text: 'Jarvis initializing...', type: 'info' })
  }, [addActivity])

  // Handle chat replies over WebSocket
  useEffect(() => {
    const onReply = (e: Event) => {
      const msg = (e as CustomEvent).detail
      const text = msg.reply || msg.text || msg.content || ''
      if (text) {
        const replyEl = document.getElementById('reply')
        if (replyEl) replyEl.textContent = text
        addActivity({ id: crypto.randomUUID(), time: new Date().toISOString(), text: `🤖 ${text.slice(0, 120)}`, type: 'success' })
      }
    }
    window.addEventListener('jarvis-reply', onReply)
    return () => window.removeEventListener('jarvis-reply', onReply)
  }, [addActivity])

  // Keep the existing effect for auth‑related logic (now minimal)
  useEffect(() => {
    if (!isAuthenticated) return
    // Any auth‑dependent side‑effects could go here
  }, [isAuthenticated])

  return (
    <div className="layout">
      {/* Header */}
      <Header />

      {/* Left Sidebar */}
      <aside className="panel sidebar-left">
        <LeftSidebar />
      </aside>

      {/* Center - Main Content */}
      <main className="center">
        {/* Orb Section */}
        <div className="panel orb-container">
          <OrbContainer />
        </div>

        {/* Remote Control */}
        <div className="panel">
          <RemoteControl />
        </div>

        {/* Face Unlock */}
        <div className="panel" id="facePanel">
          <FaceUnlock />
        </div>

        {/* Screen Preview */}
        <div className="panel" id="screenPanel">
          <ScreenPreview />
        </div>

        {/* Safety Banner */}
        <SafetyBanner />

        {/* Reply Box */}
        <div className="panel">
          <ReplyBox />
        </div>

        {/* Input Row */}
        <div className="panel">
          <InputRow />
        </div>
      </main>

      {/* Right Sidebar */}
      <aside className="panel sidebar-right" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <RightSidebar />
      </aside>

      {/* Footer */}
      <footer className="footer">
        <span>JARVIS LOCAL · GEMINI CLOUD · WHISPER.CPP</span>
        <span id="footerTime">--</span>
        <span>MAC MINI M1 · 8GB · SAFETY v1.0</span>
      </footer>
    </div>
  )
}

export default App
