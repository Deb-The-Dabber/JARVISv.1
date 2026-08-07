import { useStore } from '../../stores/useAppStore';

export function SystemMonitor() {
  const { system, setSystem } = useStore();

  // In a real app, this would fetch from /system endpoint
  // For now, return placeholder
  return (
    <div>
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
    </div>
  );
}