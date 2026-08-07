import { useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Orb } from './components/Orb/Orb'
import { Waveform } from './components/Voice/Waveform'
import { useAppStore } from './stores/useAppStore'
import { useAuthStore } from './stores/useAuthStore'
import { OrbContainer } from './components/Orb/OrbContainer'
import { SystemMonitor } from './components/Panels/SystemMonitor'
import { ActivityFeed } from './components/Panels/ActivityFeed'
import { MemoryPanel } from './components/Panels/MemoryPanel'
import { ProviderHealth } from './components/Panels/ProviderHealth'
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
import { useAudio } from './hooks/useAudio'

function App() {
  const { fallbackMode, setFallbackMode } = useAppStore()
  const { isAuthenticated } = useAuthStore()
  // Initialize WebSocket connection (hook runs its own effect)
  useWebSocket()

  // Optionally manage a local ready flag if needed
  const [wsReady, setWsReady] = useState(false)

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
