import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

export const OrbStateValues = {
  IDLE: 'idle',
  LISTENING: 'listening',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  BLOCKED: 'blocked',
  WARNING: 'warning',
} as const;
export type OrbStateType = typeof OrbStateValues[keyof typeof OrbStateValues];

export interface SystemStats {
  cpu: number;
  ram: number;
  disk: { free: number; total: number };
  network: { up: number; down: number };
}

export interface Activity {
  id: string;
  time: string;
  text: string;
  type: 'success' | 'warning' | 'error' | 'blocked' | 'info';
}

export interface ProviderHealthEntry {
  name: string;
  health?: number;
  health_pct?: number;
  circuit_open?: boolean;
  avg_latency?: number;
  successes?: number;
  failures?: number;
  status?: string;
  latency?: number;
  last_check?: string;
}

export interface MemoryStats {
  explicit_memories?: number;
  vector_entries?: number;
  rag_chunks?: number;
  graph_entities?: number;
  procedures?: number;
  associations?: number;
}

export interface AppState {
  // Orb state
  orb: { state: OrbStateType };
  setOrbState: (state: OrbStateType) => void;
  // System
  system: SystemStats | null;
  setSystem: (s: SystemStats) => void;
  // Provider health
  providerHealth: ProviderHealthEntry[];
  setProviderHealth: (h: ProviderHealthEntry[]) => void;
  // Memory
  memoryStats: MemoryStats | null;
  setMemoryStats: (m: MemoryStats) => void;
  // Activity feed
  activities: Activity[];
  addActivity: (a: Activity) => void;
  // Safety
  safetyBanner: { message: string; type: 'warning' | 'blocked' } | null;
  showSafetyBanner: (msg: string, type: 'warning' | 'blocked') => void;
  hideSafetyBanner: () => void;
  // Connection
  connected: boolean;
  setConnected: (c: boolean) => void;
  fallbackMode: boolean;
  setFallbackMode: (f: boolean) => void;
}

export const useAppStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        orb: { state: OrbStateValues.IDLE },
        setOrbState: (state: OrbStateType) => set({ orb: { state } }),
        system: null,
        setSystem: (s) => set({ system: s }),
        providerHealth: [],
        setProviderHealth: (h) => set({ providerHealth: h }),
        memoryStats: null,
        setMemoryStats: (m) => set({ memoryStats: m }),
        activities: [],
        addActivity: (a) =>
          set((s) => ({ activities: [a, ...s.activities.slice(0, 29)] })),
        safetyBanner: null,
        showSafetyBanner: (msg: string, type: 'warning' | 'blocked') =>
          set({ safetyBanner: { message: msg, type } }),
        hideSafetyBanner: () => set({ safetyBanner: null }),
        connected: false,
        setConnected: (c) => set({ connected: c }),
        fallbackMode: false,
        setFallbackMode: (f) => set({ fallbackMode: f }),
      }),
      {
        name: 'jarvis-app',
        partialize: (s) => ({ activities: s.activities.slice(0, 10) }),
        merge: (persisted, current) => {
          const p = persisted as any;
          if (p && Array.isArray(p.state?.activities)) {
            p.state.activities = p.state.activities.filter(
              (a: any) => !String(a.id).startsWith('init-')
            );
          }
          return { ...current, ...(p?.state ?? {}) };
        },
      }
    )
  )
);

// Compatibility alias — many components import { useStore }
export const useStore = useAppStore;
