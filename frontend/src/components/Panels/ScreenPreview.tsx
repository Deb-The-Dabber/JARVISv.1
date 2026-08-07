import { useState } from 'react';

export function ScreenPreview() {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState('');

  const refreshScreen = async () => {
    const img = document.getElementById('screenPreview') as HTMLImageElement;
    const analysisDiv = document.getElementById('screenAnalysis')!;
    analysisDiv.textContent = 'Loading...';
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/screen/latest?t=${Date.now()}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setPreviewUrl(url);
        analysisDiv.textContent = '✅ Screenshot loaded';
      } else {
        analysisDiv.textContent = '❌ No screenshot available';
      }
    } catch(e) {
      analysisDiv.textContent = `Error: ${(e as Error).message}`;
    }
  };

  const analyzeScreen = async () => {
    const analysisDiv = document.getElementById('screenAnalysis')!;
    analysisDiv.textContent = 'Analyzing...';
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/screen/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Api-Key': localStorage.getItem('jarvis_api_key') || '' },
        body: JSON.stringify({ question: 'Describe what is on this screen.' })
      });
      const data = await res.json();
      analysisDiv.textContent = data.analysis || 'No analysis returned.';
    } catch(e) {
      analysisDiv.textContent = `Error: ${(e as Error).message}`;
    }
  };

  return (
    <div id="screenPanel">
      <div className="panel-title">Screen Preview</div>
      <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
        <button className="btn btn-ghost" onClick={refreshScreen} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>📷 Refresh</button>
        <button className="btn btn-ghost" onClick={analyzeScreen} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>🔍 Analyze</button>
      </div>
      <img id="screenPreview" style={{ width: '100%', borderRadius: '4px', display: 'none', border: '1px solid var(--border)' }} />
      <div id="screenAnalysis" style={{ fontSize: '0.75rem', color: 'var(--fg-dim)', marginTop: '6px', minHeight: '20px' }}></div>
    </div>
  );
}