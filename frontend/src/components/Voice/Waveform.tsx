import { useStore } from '../../stores/useAppStore';
import { useMemo } from 'react';

export function Waveform() {
  const { orb } = useStore();
  const bars = 32;

  const heights = useMemo(() => {
    const base = Array(bars).fill(0).map(() => Math.random() * 0.3);
    if (orb.state === 'listening') {
      return base.map(h => h + Math.random() * 0.7);
    }
    if (orb.state === 'speaking') {
      return base.map(h => h + Math.random() * 0.5);
    }
    return base;
  }, [orb.state]);

  return (
    <div className="waveform" style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      gap: '3px', 
      height: '40px' 
    }}>
      {heights.map((h, i) => (
        <div
          key={i}
          className="wave-bar"
          style={{
            width: '3px',
            height: `${Math.max(4, h * 40)}px`,
            background: orb.state === 'listening' ? '#ef5350' : 
                       orb.state === 'speaking' ? '#69ff47' : '#4fc3f7',
            borderRadius: '2px',
            opacity: orb.state === 'idle' ? 0.3 : 1,
            transition: 'height 0.1s ease',
            animation: orb.state === 'listening' || orb.state === 'speaking' 
              ? `wave 0.6s ease-in-out infinite` 
              : 'none',
            animationDelay: `${i * 0.05}s`
          }}
        />
      ))}
    </div>
  );
}