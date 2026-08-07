import { useEffect, useState } from 'react';
import { useStore } from '../../stores/useAppStore';
import { useAuthStore } from '../../stores/useAuthStore';

export function LeftSidebar() {
  const { providerHealth, setProviderHealth, activities, addActivity, safetyBanner, showSafetyBanner, hideSafetyBanner, connected, setConnected, fallbackMode, setFallbackMode } = useStore();
  const { isAuthenticated } = useAuthStore();
  const [apiKeyValid, setApiKeyValid] = useState(false);
  const [remoteKey, setRemoteKey] = useState('');

  useEffect(() => {
    const checkApiKey = async () => {
      const stored = localStorage.getItem('jarvis-api-key');
      if (stored) {
        try {
          const res = await fetch(`${import.meta.env.VITE_API_URL}/api/key`, {
            headers: { 'X-Api-Key': stored }
          });
          if (res.ok) {
            const data = await res.json();
            setApiKeyValid(true);
            setRemoteKey(data.api_key || stored);
            document.getElementById('remoteStatusText')!.textContent = '✅ Connected';
            document.getElementById('remoteKeyDisplay')!.textContent = data.api_key || 'no key';
            document.getElementById('apiKeyInputRow')!.style.display = 'none';
            if (!stored && data.api_key) {
              localStorage.setItem('jarvis-api-key', data.api_key);
            }
          } else {
            document.getElementById('remoteStatusText')!.textContent = '❌ Invalid key';
            document.getElementById('apiKeyInputRow')!.style.display = 'block';
          }
        } catch(e) {
          document.getElementById('remoteStatusText')!.textContent = '❌ Invalid key';
          document.getElementById('apiKeyInputRow')!.style.display = 'block';
        }
      } else {
        document.getElementById('remoteStatusText')!.textContent = '❌ No key';
        document.getElementById('apiKeyInputRow')!.style.display = 'block';
      }
    };
    const fetchSystem = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/system`);
        if (res.ok) {
          const data = await res.json();
          // Update UI values directly (matches existing DOM IDs)
          const cpuPct = data.cpu?.pct ?? 0;
          const ramPct = data.ram?.pct ?? 0;
          const diskFree = data.disk?.free ?? 0;
          const diskTotal = data.disk?.total ?? 0;
          document.getElementById('cpuVal')!.textContent = `${cpuPct?.toFixed(0) ?? '--'}%`;
          document.getElementById('cpuBar')!.style.width = `${cpuPct ?? 0}%`;
          document.getElementById('ramVal')!.textContent = `${ramPct?.toFixed(0) ?? '--'}%`;
          document.getElementById('ramBar')!.style.width = `${ramPct ?? 0}%`;
          document.getElementById('diskVal')!.textContent = `${diskFree?.toFixed(0) ?? '--'} GB`;
          // Approximate usage bar (e.g., free/total)
          const diskUsage = diskTotal ? ((diskTotal - diskFree) / diskTotal) * 100 : 0;
          document.getElementById('diskBar')!.style.width = `${diskUsage}%`;
        }
      } catch (e) {
        console.error('Failed to fetch system stats', e);
      }
    };
    const fetchProviderHealth = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/health/providers`);
        if (res.ok) {
          const data = await res.json();
          // Convert dict to array of entries
          const entries = Object.entries(data).map(([name, entry]) => ({ name, ...(entry as Record<string, any>) }));
          setProviderHealth(entries);
        }
      } catch (e) {
        console.error('Failed to fetch provider health', e);
      }
    };
    // Run them
    checkApiKey();
    fetchSystem();
    fetchProviderHealth();
  }, [isAuthenticated]);

  const oauthConnect = (provider: string) => {
    const base = import.meta.env.VITE_API_URL || '';
    window.location.href = `${base}/oauth/authorize/${provider}`;
  };

  const triggerLearning = () => {
    const input = document.getElementById('learnerTaskInput') as HTMLInputElement;
    if (!input?.value) return;
    fetch(`${import.meta.env.VITE_API_URL}/learner/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: input.value })
    }).then(() => { input.value = ''; });
  };

  const saveApiKey = () => {
    const input = document.getElementById('apiKeyInput') as HTMLInputElement;
    const key = input?.value;
    if (!key) return;
    localStorage.setItem('jarvis-api-key', key);
    checkApiKey();
    input.value = '';
  };

  const copyApiKey = () => {
    const key = localStorage.getItem('jarvis-api-key') || '';
    navigator.clipboard.writeText(key);
    alert('Copied!');
  };

  const copyRemoteKey = () => {
    navigator.clipboard.writeText(remoteKey);
    alert('Copied!');
  };

  const checkApiKey = async () => {
    const stored = localStorage.getItem('jarvis-api-key');
    if (stored) {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/api/key`, {
          headers: { 'X-Api-Key': stored }
        });
        if (res.ok) {
          const data = await res.json();
          setApiKeyValid(true);
          setRemoteKey(data.api_key || stored);
          document.getElementById('remoteStatusText')!.textContent = '✅ Connected';
          document.getElementById('remoteKeyDisplay')!.textContent = data.api_key || 'no key';
          document.getElementById('apiKeyInputRow')!.style.display = 'none';
          if (!stored && data.api_key) {
            localStorage.setItem('jarvis-api-key', data.api_key);
          }
        } else {
          document.getElementById('remoteStatusText')!.textContent = '❌ Invalid key';
          document.getElementById('apiKeyInputRow')!.style.display = 'block';
        }
      } catch(e) {
        document.getElementById('remoteStatusText')!.textContent = '❌ Invalid key';
        document.getElementById('apiKeyInputRow')!.style.display = 'block';
      }
    } else {
      document.getElementById('remoteStatusText')!.textContent = '❌ No key';
      document.getElementById('apiKeyInputRow')!.style.display = 'block';
    }
  };

  return (
    <aside className="panel sidebar-left">
      <div className="panel-title">System Monitor</div>
      <div className="stat-grid">
        <div className="stat-item">
          <div className="stat-label">CPU <span id="cpuVal">--%</span></div>
          <div className="stat-bar"><div className="stat-fill" id="cpuBar" style={{ width: '0%' }}></div></div>
        </div>
        <div className="stat-item">
          <div className="stat-label">RAM <span id="ramVal">--%</span></div>
          <div className="stat-bar"><div className="stat-fill" id="ramBar" style={{ width: '0%' }}></div></div>
        </div>
        <div className="stat-item">
          <div className="stat-label">DISK <span id="diskVal">-- GB</span></div>
          <div className="stat-bar"><div className="stat-fill" id="diskBar" style={{ width: '0%' }}></div></div>
        </div>
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Active Tools</div>
      <div id="toolsList" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', lineHeight: '2' }}>
        Loading...
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Safety Log</div>
      <div id="safetyLog" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', maxHeight: '120px', overflowY: 'auto', lineHeight: '1.8' }}>
        No actions logged yet.
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Memory Systems</div>
      <div id="memoryStatus" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', lineHeight: '2' }}>
        Loading...
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Provider Health</div>
      <div id="providerHealth" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', lineHeight: '1.8' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr style={{ color: 'var(--fg-dim)' }}>
            <th style={{ textAlign: 'left' }}>Provider</th>
            <th style={{ textAlign: 'right' }}>Health</th>
            <th style={{ textAlign: 'right' }}>S/F</th>
            <th style={{ textAlign: 'right' }}>Lat.</th>
          </tr></thead>
          <tbody id="providerHealthBody">
            <tr><td colSpan={4} style={{ textAlign: 'center' }}>Loading...</td></tr>
          </tbody>
        </table>
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Remote Access</div>
      <div id="remoteKeyStatus" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', lineHeight: '2' }}>
        <div>Status: <span id="remoteStatusText">checking...</span></div>
        <div>Key: <span id="remoteKeyDisplay" style={{ fontSize: '0.55rem', wordBreak: 'break-all' }}>---</span></div>
        <div id="apiKeyInputRow" style={{ display: 'none', marginTop: '6px' }}>
          <input type="password" id="apiKeyInput" placeholder="Paste API key" 
                 style={{ width: '100%', fontSize: '0.6rem', padding: '4px 8px', background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--fg)', marginBottom: '4px' }} />
          <div style={{ display: 'flex', gap: '4px' }}>
            <button className="btn btn-primary" onClick={saveApiKey} style={{ fontSize: '0.6rem', padding: '4px 8px', flex: '1' }}>Save</button>
            <button className="btn btn-ghost" onClick={copyApiKey} style={{ fontSize: '0.65rem', padding: '4px 8px' }}>📋 Copy Key</button>
          </div>
        </div>
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Integrations</div>
      <div id="integrationsList" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', lineHeight: '2' }}>
        <div className="integration-item" data-provider="gmail">
          <span>📧 Gmail</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('gmail')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="github">
          <span>🐙 GitHub</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('github')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="google_drive">
          <span>📁 Drive</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('google_drive')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="google_sheets">
          <span>📊 Sheets</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('google_sheets')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="google_docs">
          <span>📝 Docs</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('google_docs')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="google_slides">
          <span>📽 Slides</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('google_slides')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="google_forms">
          <span>📋 Forms</span>
          <span className="integration-status disconnected">Disconnected</span>
          <button className="btn btn-ghost" onClick={() => oauthConnect('google_forms')} style={{ fontSize: '0.6rem', padding: '2px 8px' }}>Connect</button>
        </div>
        <div className="integration-item" data-provider="reminders">
          <span>📋 Reminders</span>
          <span className="integration-status connected">Ready</span>
        </div>
      </div>

      <div className="panel-title" style={{ marginTop: '20px' }}>Learner</div>
      <div id="learnerPanel" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)' }}>
        <div id="learnerStats" style={{ marginBottom: '6px' }}></div>
        <div id="learnerTools" style={{ marginBottom: '6px' }}></div>
        <div style={{ display: 'flex', gap: '4px', marginTop: '6px' }}>
          <input id="learnerTaskInput" type="text" placeholder="What should I learn?" style={{ flex: '1', fontSize: '0.65rem', padding: '4px 6px', background: 'var(--bg)', color: 'var(--fg)', border: '1px solid var(--border)', borderRadius: '4px' }} />
          <button className="btn btn-ghost" onClick={triggerLearning} style={{ fontSize: '0.6rem', padding: '4px 8px' }}>Teach</button>
        </div>
      </div>
    </aside>
  );
}