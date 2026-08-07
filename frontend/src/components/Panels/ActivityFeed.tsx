import { useStore } from '../../stores/useAppStore';

export function ActivityFeed() {
  const { activities, addActivity } = useStore();

  return (
    <div className="activity-feed" id="activityFeed">
      {activities.length === 0 ? (
        <div className="activity-item">
          <span className="activity-time">--:--</span>
          <span className="activity-text">Jarvis initializing...</span>
        </div>
      ) : (
        activities.map((a) => (
          <div key={a.id} className={`activity-item ${a.type}`}>
            <span className="activity-time">{a.time}</span>
            <span className="activity-text">{a.text}</span>
          </div>
        ))
      )}
    </div>
  );
}