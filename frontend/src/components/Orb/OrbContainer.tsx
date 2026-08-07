import { useStore } from '../../stores/useAppStore';
import { Orb } from './Orb';
import { Waveform } from '../Voice/Waveform';
import { Canvas } from '@react-three/fiber';

export function OrbContainer() {
  const { orb } = useStore();

  return (
    <div className="orb-container">
      {/* Three.js canvas for the orb */}
      <Canvas style={{ width: 120, height: 120 }}>
        <Orb />
      </Canvas>
      <div className="orb-status" id="orbStatus">STANDBY</div>
      <Waveform />
    </div>
  );
}