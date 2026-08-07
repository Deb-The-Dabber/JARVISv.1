import { useStore } from '../../stores/useAppStore';

export function RightSidebar() {
  const { activities, addActivity } = useStore();

  return (
    <aside className="panel sidebar-right" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div>
        <div className="panel-title">Activity Feed</div>
        <div className="activity-feed" id="activityFeed">
          <div className="activity-item">
            <span className="activity-time">--:--</span>
            <span className="activity-text">Jarvis initializing...</span>
          </div>
        </div>
      </div>
      <div>
        <div className="panel-title">Memory</div>
        <div className="memory-list" id="memoryList">
          <div className="memory-item">No memories loaded yet.</div>
        </div>
      </div>
    </aside>
  );
}