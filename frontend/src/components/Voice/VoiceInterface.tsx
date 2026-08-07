import { useState, useCallback } from 'react';
import { useStore } from '../../stores/useAppStore';
import { Waveform } from './Waveform';
import { useWebSocket } from '../../hooks/useWebSocket';
import { useAudio } from '../../hooks/useAudio';

export function VoiceInterface() {
  const { connected } = useStore();
  const { sendText, sendEndAudio } = useWebSocket();
  const { isRecording, startRecording, stopRecording } = useAudio();
  const [ttsOnPhone, setTtsOnPhone] = useState(true);
  const [input, setInput] = useState('');

  const handleMicToggle = useCallback(async () => {
    if (isRecording) {
      await stopRecording();
      sendEndAudio();
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording, sendEndAudio]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    sendText(trimmed);
    setInput('');
  };

  return (
    <div className="voice-interface">
      <Waveform />
      <div className="input-row" style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
        <input
          type="text"
          id="textInput"
          placeholder="Enter command..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <button className="btn btn-primary" id="micBtn" onClick={handleMicToggle}>
          {isRecording ? 'STOP' : 'MIC'}
        </button>
        <button className="btn btn-ghost" onClick={() => {/* stop TTS placeholder */}}>
          STOP
        </button>
        <button className="btn btn-ghost" onClick={handleSend}>
          SEND
        </button>
      </div>
      <div className="tts-toggle" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
        <input type="checkbox" id="ttsClientToggle" checked={ttsOnPhone} onChange={(e) => setTtsOnPhone(e.target.checked)} />
        <label htmlFor="ttsClientToggle">📱 TTS on this device</label>
        <span id="ttsStatus" style={{ marginLeft: 'auto', fontSize: '0.7rem' }}></span>
      </div>
    </div>
  );
}
