import { useStore } from '../stores/useAppStore';

export function ReplyBox() {
  const { connected } = useStore();

  return (
    <div className="panel">
      <div className="reply-box">
        <div className="label">// Jarvis Response</div>
        <div id="reply">Systems online. Ready for input.</div>
      </div>
    </div>
  );
}