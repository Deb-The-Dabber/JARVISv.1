import { useState, useEffect } from 'react';
import { useStore } from '../../stores/useAppStore';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function Header() {
  const { connected } = useStore();
  const [online, setOnline] = useState(connected);
  const [model, setModel] = useState('MODEL');
  const [time, setTime] = useState('--:--:--');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
      setTime(`${dateStr} · ${timeStr}`);
      const footerTime = document.getElementById('footerTime');
      if (footerTime) footerTime.textContent = timeStr;
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  // Poll /health like the static UI — drives ONLINE/OFFLINE + model name
  useEffect(() => {
    const checkServer = async () => {
      try {
        const res = await fetch(`${API}/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOnline(true);
        const runtime = data.runtime || {};
        const last = runtime.model_last_used;
        const pref = runtime.model_preferred;
        setModel((last && last !== 'unknown' ? last : pref) || 'MODEL');
      } catch (e) {
        setOnline(false);
      }
    };
    checkServer();
    const id = setInterval(checkServer, 20000);
    return () => clearInterval(id);
  }, []);

  const isOnline = online;

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
          <div className={isOnline ? "dot" : "dot offline"} id="serverDot"></div>
          <span id="serverStatus">{isOnline ? "ONLINE" : "OFFLINE"}</span>
        </div>
        <div className="status-item">
          <div className={isOnline ? "dot" : "dot offline"} id="modelDot"></div>
          <span id="modelStatus">{model}</span>
        </div>
        <div className="status-item" id="timeDisplay">{time}</div>
      </div>
    </header>
  );
}
