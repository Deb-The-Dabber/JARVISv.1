import { useFrame } from '@react-three/fiber';
import { useStore } from '../../stores/useAppStore';
import * as THREE from 'three';
import { useRef, useState, useEffect, useMemo } from 'react';

const ORB_STATES = {
  idle: { color: '#4fc3f7', emissive: '#004466', scale: 1, pulse: false },
  listening: { color: '#ef5350', emissive: '#660022', scale: 1.05, pulse: true },
  thinking: { color: '#ffa726', emissive: '#664400', scale: 1.02, pulse: true },
  speaking: { color: '#69ff47', emissive: '#003322', scale: 1.03, pulse: true },
  blocked: { color: '#ef5350', emissive: '#660011', scale: 1.08, pulse: true },
  warning: { color: '#ffa726', emissive: '#664400', scale: 1.04, pulse: true },
};

function RingMesh({ radius, width, color, opacity, rotation }: { radius: number; width: number; color: string; opacity: number; rotation: number[] }) {
  const geometry = useMemo(
    () => new THREE.RingGeometry(radius - width / 2, radius + width / 2, 64),
    [radius, width]
  );
  const material = useMemo(
    () => new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide }),
    [color, opacity]
  );
  // rotation expects Euler order; three components as array
  const rot = rotation as unknown as [number, number, number];
  return <mesh geometry={geometry} material={material} rotation={rot} />;
}

export function Orb() {
  const { orb } = useStore();
  const meshRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Group>(null);
  const [material] = useState(() => new THREE.MeshStandardMaterial({
    color: new THREE.Color(0x4fc3f7),
    metalness: 0.3,
    roughness: 0.2,
    emissive: new THREE.Color(0x004466),
    emissiveIntensity: 0.5,
  }));

  const state = ORB_STATES[orb.state];

  useFrame((_, delta) => {
    if (state.pulse) {
      const pulse = 1 + Math.sin(performance.now() * 0.003) * 0.03;
      material.emissiveIntensity = 0.5 + Math.sin(performance.now() * 0.005) * 0.3;
      if (meshRef.current) meshRef.current.scale.setScalar(state.scale * pulse);
    }

    if (ringRef.current) {
      ringRef.current.rotation.y += delta * 0.1;
      ringRef.current.rotation.x += delta * 0.03;
    }
  });

  useEffect(() => {
    if (material) {
      material.color.set(state.color);
      material.emissive.set(state.emissive);
    }
  }, [orb.state]);

  return (
    <group>
      <group ref={ringRef}>
        {/* Rings rendered as meshes */}
        <RingMesh radius={70} width={0.5} color="#4fc3f7" opacity={0.15} rotation={[Math.PI / 2, 0, 0]} />
        <RingMesh radius={85} width={0.3} color="#69ff47" opacity={0.1} rotation={[0, Math.PI / 4, 0]} />
        <RingMesh radius={100} width={0.2} color="#ffa726" opacity={0.08} rotation={[Math.PI / 3, 0, Math.PI / 6]} />
      </group>

      <mesh ref={meshRef} onClick={() => useStore.getState().setOrbState('listening')}>
        <sphereGeometry args={[40, 64, 64]} />
        <meshStandardMaterial
          ref={material}
          color={state.color}
          metalness={0.3}
          roughness={0.2}
          emissive={state.emissive}
          emissiveIntensity={0.5}
        />
      </mesh>

      <pointLight
        position={[0, 0, 100]}
        color="#4fc3f7"
        intensity={2}
        distance={300}
        decay={2}
      />
    </group>
  );
}