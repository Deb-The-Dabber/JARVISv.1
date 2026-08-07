import { useState } from 'react';
import { useStore } from '../stores/useAppStore';
import { useAuthStore } from '../stores/useAuthStore';

export function InputRow() {
  const [text, setText] = useState('');
  const { fallbackMode, setFallbackMode } = useStore();
  const { isAuthenticated } = useAuthStore();

  const handleSend = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setText('');
    const lower = trimmed.toLowerCase();
    const yesWords = ['yes', 'yeah', 'go ahead', 'confirm', 'sure', 'ok', 'approved'];
    const noWords = ['no', 'cancel', 'stop', 'nevermind', 'deny'];

    if (yesWords.some((w) => lower.includes(w))) {
      window.dispatchEvent(new CustomEvent('jarvis-confirm', { detail: true }));
      return;
    }
    if (noWords.some((w) => lower.includes(w))) {
      window.dispatchEvent(new CustomEvent('jarvis-confirm', { detail: false }));
      return;
    }
    window.dispatchEvent(new CustomEvent('jarvis-text', { detail: trimmed }));
  };

  return (
    <div className="panel">
      <div className="input-row">
        <input
          type="text"
          id="textInput"
          placeholder="Enter command..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <button className="btn btn-primary" id="micBtn" onClick={handleSend}>
          SEND
        </button>
        <button className="btn btn-ghost" onClick={() => window.dispatchEvent(new CustomEvent('jarvis-stop'))}>
          STOP
        </button>
      </div>
      <div
        className="tts-toggle"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginTop: '8px',
          fontSize: '0.75rem',
          color: 'var(--fg-dim)',
        }}
      >
        <input type="checkbox" id="ttsClientToggle" checked />
        <label htmlFor="ttsClientToggle">📱 TTS on this device</label>
        <span id="ttsStatus" style={{ marginLeft: 'auto', fontSize: '0.7rem' }}></span>
      </div>
    </div>
  );
}
