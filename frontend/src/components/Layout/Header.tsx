import { useState, useEffect } from 'react';
import { useStore } from '../../stores/useAppStore';
import { useAuthStore } from '../../stores/useAuthStore';

export function Header() {
  const { connected, setConnected } = useStore();
  const { isAuthenticated } = useAuthStore();
  const [time, setTime] = useState('');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      document.getElementById('footerTime')!.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  // Fetch runtime status to display current model
  useEffect(() => {
    if (!connected) return;
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/health`);
        if (res.ok) {
          const data = await res.json();
          const model = data.model_last_used || data.model_preferred || 'MODEL';
          document.getElementById('modelStatus')!.textContent = model;
        }
      } catch (e) {
        console.error('Failed to fetch model status', e);
      }
    };
    fetchStatus();
  }, [connected]);

  return (
    <header className="header">
      <div className="logo">
        <div>
          <h1>J.A.R.V.I.S.</h1>
          <div className="version">JUST A RATHER VERY INTELLIGENT SYSTEM · v3.1</div>
        </div>
      </div>
      <div className="status-bar">
        <div className="status-item">
          <div className={connected ? "dot" : "dot offline"} id="serverDot"></div>
          <span id="serverStatus">{connected ? "CONNECTED" : "CONNECTING"}</span>
        </div>
        <div className="status-item">
          <div className="dot" id="modelDot"></div>
          <span id="modelStatus">MODEL</span>
        </div>
        <div className="status-item" id="timeDisplay">--:--:--</div>
      </div>
    </header>
  );
}