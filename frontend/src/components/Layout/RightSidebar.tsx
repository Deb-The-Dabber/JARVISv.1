import { useEffect, useState } from 'react';
import { useStore } from '../../stores/useAppStore';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function RightSidebar() {
  const { activities } = useStore();
  const [memories, setMemories] = useState<string[]>([]);

  useEffect(() => {
    const fetchMemories = async () => {
      try {
        const res = await fetch(`${API}/memories`);
        if (!res.ok) return;
        const data = await res.json();
        setMemories((data.memories || []).slice(0, 10).map((m: any) => m.content || m.text || JSON.stringify(m)));
      } catch (e) {}
    };
    fetchMemories();
    const id = setInterval(fetchMemories, 20000);
    return () => clearInterval(id);
  }, []);

  const feed = activities.length
    ? activities.map((a) => (
        <div className={`activity-item ${a.type}`} key={a.id}>
          <span className="activity-time">{a.time ? a.time.slice(11, 16) : '--:--'}</span>
          <span className="activity-text">{a.text}</span>
        </div>
      ))
    : (
        <div className="activity-item">
          <span className="activity-time">--:--</span>
          <span className="activity-text">All systems nominal</span>
        </div>
      );

  return (
    <aside className="panel sidebar-right" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div>
        <div className="panel-title">Activity Feed</div>
        <div className="activity-feed" id="activityFeed">
          {feed}
        </div>
      </div>
      <div>
        <div className="panel-title">Memory</div>
        <div className="memory-list" id="memoryList">
          {memories.length
            ? memories.map((m, i) => <div className="memory-item" key={i}>{m}</div>)
            : <div className="memory-item">No memories loaded yet.</div>}
        </div>
      </div>
    </aside>
  );
}
