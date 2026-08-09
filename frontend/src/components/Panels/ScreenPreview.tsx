import { useState } from 'react';

export function ScreenPreview() {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState('');
  const [loading, setLoading] = useState(false);

  const refreshScreen = async () => {
    setLoading(true);
    setAnalysis('Loading...');
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/screen/latest?t=${Date.now()}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setPreviewUrl(url);
        setAnalysis('✅ Screenshot loaded');
      } else {
        setPreviewUrl(null);
        setAnalysis('❌ No screenshot available');
      }
    } catch (e) {
      setAnalysis(`Error: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const analyzeScreen = async () => {
    setAnalysis('Analyzing...');
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/screen/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Api-Key': localStorage.getItem('jarvis_api_key') || '',
        },
        body: JSON.stringify({ text: 'Describe what is on this screen.' }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAnalysis(`❌ ${data.detail || `HTTP ${res.status}`}`);
        return;
      }
      setAnalysis(data.analysis || 'No analysis returned.');
    } catch (e) {
      setAnalysis(`Error: ${(e as Error).message}`);
    }
  };

  return (
    <div id="screenPanel">
      <div className="panel-title">Screen Preview</div>
      <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
        <button className="btn btn-ghost" onClick={refreshScreen} disabled={loading} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>📷 Refresh</button>
        <button className="btn btn-ghost" onClick={analyzeScreen} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>🔍 Analyze</button>
      </div>
      {previewUrl && (
        <img
          src={previewUrl}
          style={{ width: '100%', borderRadius: '4px', display: 'block', border: '1px solid var(--border)' }}
        />
      )}
      <div style={{ fontSize: '0.75rem', color: 'var(--fg-dim)', marginTop: '6px', minHeight: '20px' }}>{analysis}</div>
    </div>
  );
}
