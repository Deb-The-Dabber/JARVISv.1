import { useState } from 'react';

export function FaceUnlock() {
  const [enrolled, setEnrolled] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(false);
  const [faceResult, setFaceResult] = useState('');

  const checkFaceStatus = async () => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/face/status`, {
        headers: { 'X-Api-Key': localStorage.getItem('jarvis_api_key') || '' }
      });
      const data = await res.json();
      if (data.enrolled) {
        setEnrolled(true);
        document.getElementById('faceStatus')!.textContent = '✅ Face enrolled (ArcFace)';
        document.getElementById('faceControls')!.style.display = 'block';
      } else {
        document.getElementById('faceStatus')!.textContent = '⚠️ No face enrolled. Tap below to enroll.';
        document.getElementById('faceControls')!.style.display = 'block';
      }
    } catch(e) {
      document.getElementById('faceStatus')!.textContent = '❌ Could not check face status';
    }
  };

  const enrollFace = () => {
    document.getElementById('faceFileInput')!.click();
  };

  const uploadEnrollPhotos = async (files: FileList) => {
    if (!files.length) return;
    const resultDiv = document.getElementById('faceResult')!;
    resultDiv.textContent = `Uploading ${files.length} photos...`;
    const formData = new FormData();
    for (const file of files) {
      formData.append('photos', file);
    }
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/enroll/face`, {
        method: 'POST',
        headers: { 'X-Api-Key': localStorage.getItem('jarvis_api_key') || '' },
        body: formData
      });
      const data = await res.json();
      if (data.status === 'ok') {
        document.getElementById('faceResult')!.textContent = `✅ Enrolled! ${data.photos_processed}/${data.photos_total} photos processed.`;
        document.getElementById('faceStatus')!.textContent = '✅ Face enrolled (ArcFace)';
        window.dispatchEvent(new CustomEvent('jarvis-activity', { detail: { text: 'Face enrolled successfully', type: 'success' } }));
      } else {
        document.getElementById('faceResult')!.textContent = `❌ ${data.detail || 'Enrollment failed'}`;
      }
    } catch(e) {
      document.getElementById('faceResult')!.textContent = `Error: ${(e as Error).message}`;
    }
  };

  const unlockFace = () => {
    document.getElementById('unlockFileInput')!.click();
  };

  const uploadUnlockPhoto = async (file: File) => {
    if (!file) return;
    const resultDiv = document.getElementById('faceResult')!;
    resultDiv.textContent = 'Verifying...';
    const formData = new FormData();
    formData.append('photo', file);
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/unlock/face`, {
        method: 'POST',
        headers: { 'X-Api-Key': localStorage.getItem('jarvis_api_key') || '' },
        body: formData
      });
      const data = await res.json();
      if (data.authenticated) {
        resultDiv.textContent = `✅ Authenticated! Confidence: ${(data.confidence * 100).toFixed(0)}%`;
        window.dispatchEvent(new CustomEvent('jarvis-reply', { detail: { reply: '✅ Face authenticated. Welcome.', type: 'final' } }));
      } else {
        resultDiv.textContent = `❌ Not recognized (${(data.confidence * 100).toFixed(0)}% — need ${(data.threshold * 100).toFixed(0)}%)`;
        window.dispatchEvent(new CustomEvent('jarvis-activity', { detail: { text: 'Face unlock: denied', type: 'blocked' } }));
      }
    } catch(e) {
      resultDiv.textContent = `Error: ${(e as Error).message}`;
    }
  };

  return (
    <div id="facePanel">
      <div className="panel-title">Face Unlock</div>
      <div id="faceStatus" style={{ fontSize: '0.75rem', color: 'var(--fg-dim)', marginBottom: '8px' }}>Checking enrollment...</div>
      <div id="faceControls" style={{ display: 'none' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <button className="btn btn-ghost" onClick={enrollFace} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>📸 Enroll Face</button>
          <button className="btn btn-ghost" onClick={unlockFace} style={{ fontSize: '0.7rem', padding: '8px 12px' }}>🔓 Unlock</button>
        </div>
        <div id="faceResult" style={{ fontSize: '0.75rem', color: 'var(--fg-dim)', marginTop: '6px', minHeight: '20px' }}></div>
      </div>
      <input type="file" id="faceFileInput" accept="image/*" multiple style={{ display: 'none' }} onChange={(e) => { if (e.target.files) uploadEnrollPhotos(e.target.files); }} />
      <input type="file" id="unlockFileInput" accept="image/*" style={{ display: 'none' }} onChange={(e) => { const files = e.target.files; if (files && files[0]) uploadUnlockPhoto(files[0]); }} />
    </div>
  );
}