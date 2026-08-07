import { useStore } from '../../stores/useAppStore';

export function Footer() {
  const { connected } = useStore();

  return (
    <footer className="footer">
      <span>JARVIS LOCAL · GEMINI CLOUD · WHISPER.CPP</span>
      <span id="footerTime">--</span>
      <span>MAC MINI M1 · 8GB · SAFETY v1.0</span>
    </footer>
  );
}