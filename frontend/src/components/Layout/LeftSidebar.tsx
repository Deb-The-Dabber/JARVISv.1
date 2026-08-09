import { useEffect, useState } from 'react';
import { useStore } from '../../stores/useAppStore';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const ACTIVE_TOOLS = [
  'get_weather_detailed', 'web_search', 'open_app',
  'spotify_play_song', 'set_timer', 'send_imessage',
  'get_calendar_events', 'run_terminal_command',
  'take_screenshot', 'organize_downloads',
  'read_screen', 'get_recap',
];

const SAFETY_COLORS: Record<string, string> = {
  ALLOWED: 'var(--success, #4caf50)',
  BLOCKED: 'var(--danger, #f44336)',
  CONFIRMED_BY_USER: 'var(--accent, #4fc3f7)',
  DENIED_BY_USER: 'var(--warning, #ff9800)',
  EXECUTED: 'var(--fg-dim)',
};

export function LeftSidebar() {
  const { setProviderHealth } = useStore();
  const [apiKeyValid, setApiKeyValid] = useState(false);
  const [remoteKey, setRemoteKey] = useState('');

  const checkApiKey = async () => {
    const stored = localStorage.getItem('jarvis-api-key');
    const statusEl = document.getElementById('remoteStatusText');
    const keyEl = document.getElementById('remoteKeyDisplay');
    const rowEl = document.getElementById('apiKeyInputRow');
    if (!stored) {
      if (statusEl) statusEl.textContent = '❌ No key';
      if (rowEl) rowEl.style.display = 'block';
      return;
    }
    try {
      const res = await fetch(`${API}/api/key`, { headers: { 'X-Api-Key': stored } });
      if (res.ok) {
        const data = await res.json();
        setApiKeyValid(true);
        const key = data.api_key || stored;
        setRemoteKey(key);
        if (statusEl) statusEl.textContent = '✅ Connected';
        if (keyEl) keyEl.textContent = key;
        if (rowEl) rowEl.style.display = 'none';
        if (!stored && data.api_key) localStorage.setItem('jarvis-api-key', data.api_key);
      } else {
        if (statusEl) statusEl.textContent = '❌ Invalid key';
        if (rowEl) rowEl.style.display = 'block';
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = '❌ Invalid key';
      if (rowEl) rowEl.style.display = 'block';
    }
  };

  const fetchSystem = async () => {
    try {
      const res = await fetch(`${API}/system`);
      if (!res.ok) return;
      const data = await res.json();
      const cpu = Math.round(data.cpu_percent || 0);
      const ram = Math.round(data.ram_percent || 0);
      const diskFree = data.disk_free_gb || 0;
      const diskTotal = data.disk_total_gb || 1;
      const diskPct = Math.round((1 - diskFree / diskTotal) * 100);

      const cpuVal = document.getElementById('cpuVal');
      const cpuBar = document.getElementById('cpuBar');
      if (cpuVal) cpuVal.textContent = `${cpu}%`;
      if (cpuBar) cpuBar.style.width = `${cpu}%`;

      const ramVal = document.getElementById('ramVal');
      const ramBar = document.getElementById('ramBar');
      if (ramVal) ramVal.textContent = `${ram}%`;
      if (ramBar) ramBar.style.width = `${ram}%`;

      const diskVal = document.getElementById('diskVal');
      const diskBar = document.getElementById('diskBar');
      if (diskVal) diskVal.textContent = `${diskFree}GB free`;
      if (diskBar) diskBar.style.width = `${diskPct}%`;
    } catch (e) {
      console.error('Failed to fetch system stats', e);
    }
  };

  const fetchProviderHealth = async () => {
    try {
      const res = await fetch(`${API}/health/providers`);
      if (!res.ok) return;
      const data = await res.json();
      const tbody = document.getElementById('providerHealthBody');
      if (!tbody) return;

      const entries = Object.entries(data).map(([name, h]) => {
        const entry = h as Record<string, any>;
        const health = entry.health_score ?? 100;
        const color = health > 70 ? '#4caf50' : health > 30 ? '#ff9800' : '#f44336';
        const circuit = entry.circuit_open ? '🔴' : '🟢';
        return {
          name, health, color, circuit,
          successes: entry.successes || 0,
          failures: entry.failures || 0,
          latency: entry.avg_latency ? `${(entry.avg_latency * 1000).toFixed(0)}ms` : '-',
        };
      });

      setProviderHealth(entries as any);

      tbody.innerHTML = entries.length
        ? entries.map((e) => `
            <tr>
              <td style="color:${e.color}">${e.circuit} ${e.name}</td>
              <td style="text-align:right;color:${e.color}">${e.health}%</td>
              <td style="text-align:right;">${e.successes}/${e.failures}</td>
              <td style="text-align:right;">${e.latency}</td>
            </tr>`).join('')
        : '<tr><td colspan="4">No data yet</td></tr>';
    } catch (e) {
      const tbody = document.getElementById('providerHealthBody');
      if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="color:#f44336;">Offline</td></tr>';
    }
  };

  const fetchMemoryStatus = async () => {
    try {
      const res = await fetch(`${API}/memory/stats`);
      if (!res.ok) return;
      const d = await res.json();
      const el = document.getElementById('memoryStatus');
      if (el) el.innerHTML = `
        <div>Facts: ${d.explicit_memories ?? '?'} entries</div>
        <div>Vector: ${d.vector_entries ?? '?'} chunks</div>
        <div>RAG: ${d.rag_chunks ?? '?'} doc chunks</div>
        <div>Graph: ${d.graph_entities ?? '?'} entities</div>
        <div>Procedures: ${d.procedures ?? '?'} routines</div>
        <div>Associations: ${d.associations ?? '?'} pairs</div>`;
    } catch (e) {}
  };

  const fetchSafetyLog = async () => {
    try {
      const res = await fetch(`${API}/audit`);
      if (!res.ok) return;
      const data = await res.json();
      const logs = (data.logs || []).slice(0, 8);
      const el = document.getElementById('safetyLog');
      if (!el) return;
      if (!logs.length) {
        el.innerHTML = 'No actions logged yet.';
        return;
      }
      el.innerHTML = logs.map((l: any) => {
        const color = SAFETY_COLORS[l.decision] || 'var(--fg-dim)';
        return `<div style="color:${color}">${l.time ? l.time.slice(11, 16) : '--:--'} ${l.tool} → ${l.decision}</div>`;
      }).join('');
    } catch (e) {}
  };

  const fetchTools = () => {
    const el = document.getElementById('toolsList');
    if (el) el.innerHTML = ACTIVE_TOOLS.map((t) => `<div>◆ ${t}</div>`).join('');
  };

  const fetchLearner = async () => {
    try {
      const [toolsRes, statsRes] = await Promise.all([
        fetch(`${API}/learner/tools`),
        fetch(`${API}/learner/stats`),
      ]);
      const tools = await toolsRes.json();
      const stats = await statsRes.json();

      const statsEl = document.getElementById('learnerStats');
      if (statsEl) {
        statsEl.innerHTML = `<b>${stats.learned_tools_count || 0}</b> learned tool(s) · <b>${stats.total_audit_actions || 0}</b> total actions`;
        if (stats.top_tools && stats.top_tools.length) {
          statsEl.innerHTML += '<br><span style="font-size:0.6rem;">Top tools: ' + stats.top_tools.slice(0, 5).map((t: any) => t.tool).join(', ') + '</span>';
        }
      }

      const toolsEl = document.getElementById('learnerTools');
      if (toolsEl) {
        if (!tools.tools || !tools.tools.length) {
          toolsEl.innerHTML = '<span style="font-size:0.6rem;">No learned tools yet.</span>';
        } else {
          toolsEl.innerHTML = tools.tools.map((t: any) =>
            `<div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0;">
              <span style="flex:1;"><b>${t.name}</b> <span style="font-size:0.55rem;color:var(--warning);">${t.task || ''}</span></span>
              <button class="btn btn-ghost" onclick="window.deleteLearnedTool && window.deleteLearnedTool('${t.name}')" style="font-size:0.55rem;padding:1px 6px;">×</button>
            </div>`).join('');
        }
      }
    } catch (e) {
      console.warn('Failed to load learner data:', e);
    }
  };

  useEffect(() => {
    checkApiKey();
    fetchSystem();
    fetchProviderHealth();
    fetchMemoryStatus();
    fetchSafetyLog();
    fetchTools();
    fetchLearner();

    const interval = setInterval(() => {
      fetchSystem();
      fetchProviderHealth();
      fetchMemoryStatus();
      fetchSafetyLog();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  const oauthConnect = (provider: string) => {
    window.location.href = `${API}/oauth/authorize/${provider}`;
  };

  const triggerLearning = () => {
    const input = document.getElementById('learnerTaskInput') as HTMLInputElement | null;
    if (!input?.value) return;
    fetch(`${API}/learner/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: input.value }),
    }).then(() => {
      input.value = '';
      fetchLearner();
    });
  };

  const saveApiKey = () => {
    const input = document.getElementById('apiKeyInput') as HTMLInputElement | null;
    const key = input?.value;
    if (!key) return;
    localStorage.setItem('jarvis-api-key', key);
    checkApiKey();
    input!.value = '';
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
          <div className="stat-label">DISK <span id="diskVal">-- GB free</span></div>
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
