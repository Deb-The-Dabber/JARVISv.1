import { useState } from 'react';
import { useStore } from '../../stores/useAppStore';

export function RemoteControl() {
  const [result, setResult] = useState('');
  const [pendingCmd, setPendingCmd] = useState<{ command: string; params: any } | null>(null);

  const getApiKey = () => localStorage.getItem('jarvis-api-key') || '';

  const remoteCmd = async (command: string, params: any = {}) => {
    const resultDiv = document.getElementById('remoteResult');
    if (!resultDiv) return;
    resultDiv.textContent = 'Sending...';
    try {
      const payload = JSON.stringify({ command, params });
      const res = await fetch(`${import.meta.env.VITE_API_URL}/remote/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Api-Key': getApiKey() },
        body: JSON.stringify({ text: payload })
      });
      const data = await res.json();
      if (data.status === 'confirm') {
        setPendingCmd({ command, params });
        const msgEl = document.getElementById('remoteConfirmMsg');
        if (msgEl) msgEl.textContent = data.message;
        const confirmEl = document.getElementById('remoteConfirm');
        if (confirmEl) confirmEl.style.display = 'flex';
        resultDiv.textContent = 'Warning: Confirmation required';
      } else if (data.status === 'ok') {
        const result = typeof data.result === 'string' ? data.result : JSON.stringify(data.result);
        setResult(result.substring(0, 200));
        window.dispatchEvent(new CustomEvent('jarvis-activity', { detail: { text: `Remote: ${command} -> ${result.substring(0, 60)}`, type: 'success' } }));
      } else {
        resultDiv.textContent = `Error: ${data.detail || 'Unknown'}`;
      }
    } catch(e) {
      resultDiv.textContent = `Error: ${(e as Error).message}`;
    }
  };

  const remoteCmdPrompt = (command: string) => {
    const appName = prompt('App name:');
    if (appName) remoteCmd(command, { app_name: appName });
  };

  const remoteConfirmYes = async () => {
    if (pendingCmd) {
      document.getElementById('remoteConfirm')!.style.display = 'none';
      const resultDiv = document.getElementById('remoteResult');
      resultDiv!.textContent = 'Confirming...';
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/remote/confirm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Api-Key': localStorage.getItem('jarvis-api-key') || '' },
          body: JSON.stringify({ text: JSON.stringify(pendingCmd) })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          const result = typeof data.result === 'string' ? data.result : JSON.stringify(data.result);
          setResult(result.substring(0, 200));
          window.dispatchEvent(new CustomEvent('jarvis-activity', { detail: { text: `Remote confirmed: ${pendingCmd.command}`, type: 'success' } }));
        }
      } catch(e) {
        const resultDiv = document.getElementById('remoteResult');
        if (resultDiv) resultDiv.textContent = `Error: ${(e as Error).message}`;
      }
      setPendingCmd(null);
    }
  };

  const remoteConfirmNo = () => {
    const confirmEl = document.getElementById('remoteConfirm');
    if (confirmEl) confirmEl.style.display = 'none';
    const resultDiv = document.getElementById('remoteResult');
    if (resultDiv) resultDiv.textContent = 'Cancelled.';
    setPendingCmd(null);
  };

  return (
    <div>
      <div className="panel-title">Remote Control</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
        <button className="btn btn-ghost" onClick={() => remoteCmd('weather')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Weather</button>
        <button className="btn btn-ghost" onClick={() => remoteCmd('system_status')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>System</button>
        <button className="btn btn-ghost" onClick={() => remoteCmd('screen_check')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Screen</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('open_app')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Open App</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('quit_app')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Quit App</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('send_imessage')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Message</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('gmail_search')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Search Email</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('github_search_code')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Search Code</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('github_create_issue')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Create Issue</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('reminders_list')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>List Reminders</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('reminders_create')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Add Reminder</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('gdrive_list')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>List Drive</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('gdrive_search')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Search Drive</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('gdrive_upload')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Upload File</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('gsheets_read_range')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Read Sheet</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('gsheets_append')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Append Row</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('docs_get')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Get Doc</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('docs_create')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>New Doc</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('slides_get')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Get Slide</button>
        <button className="btn btn-ghost" onClick={() => remoteCmdPrompt('forms_get')} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>Get Form</button>
      </div>
      <div id="remoteResult" style={{ fontSize: '0.75rem', color: 'var(--fg-dim)', minHeight: '20px' }}></div>
      <div id="remoteConfirm" style={{ display: 'none', marginTop: '6px', gap: '6px', alignItems: 'center' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--warning)' }} id="remoteConfirmMsg"></span>
        <button className="btn btn-primary" onClick={remoteConfirmYes} style={{ fontSize: '0.7rem', padding: '6px 14px' }}>YES</button>
        <button className="btn btn-ghost" onClick={remoteConfirmNo} style={{ fontSize: '0.7rem', padding: '6px 14px' }}>NO</button>
      </div>
    </div>
  );
}