import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  AutomationSession,
  TaskType,
  AutomationState,
  IDEType,
  AutomationTemplate,
} from '../types';

interface AutomationStore {
  // Current session
  currentSession: AutomationSession | null;
  setCurrentSession: (session: AutomationSession | null) => void;

  // Sessions list (unused but kept for compatibility)
  sessions: AutomationSession[];
  setSessions: (sessions: AutomationSession[]) => void;
  addSession: (session: AutomationSession) => void;
  updateSession: (id: string, updates: Partial<AutomationSession>) => void;

  // Templates (unused placeholder)
  templates: AutomationTemplate[];
  setTemplates: (templates: AutomationTemplate[]) => void;
  addTemplate: (template: AutomationTemplate) => void;
  updateTemplate: (id: string, updates: Partial<AutomationTemplate>) => void;
  deleteTemplate: (id: string) => void;

  // Execution helpers (no UI integration in frontend for now)
  startAutomation: (taskDescription: string) => Promise<string>;
  handleUserResponse: (response: string) => Promise<string>;
  getStatus: () =>
    | {
        sessionId: string;
        state: string;
        task: string;
        type: string;
        ide: string | null;
        folder: string | null;
      }
    | null;
  cancelAutomation: () => string;
  _saveSession: () => void;
}

export const useAutomationStore = create<AutomationStore>()(
  devtools(
    persist(
      (set, get) => ({
        currentSession: null,
        setCurrentSession: (session) => set({ currentSession: session }),
        sessions: [],
        setSessions: (sessions) => set({ sessions }),
        addSession: (session) => set((s) => ({ sessions: [session, ...s.sessions] })),
        updateSession: (id, updates) =>
          set((s) => ({
            sessions: s.sessions.map((sess) => (sess.session_id === id ? { ...sess, ...updates } : sess)),
            currentSession:
              s.currentSession && s.currentSession.session_id === id
                ? { ...s.currentSession, ...updates }
                : s.currentSession,
          })),
        templates: [],
        setTemplates: (templates) => set({ templates }),
        addTemplate: (template) => set((s) => ({ templates: [template, ...s.templates] })),
        updateTemplate: (id, updates) =>
          set((s) => ({
            templates: s.templates.map((t) => (t.id === id ? { ...t, ...updates } : t)),
          })),
        deleteTemplate: (id) => set((s) => ({ templates: s.templates.filter((t) => t.id !== id) })),
        // Minimal automation flow – placeholder implementations
        startAutomation: async (taskDescription: string) => {
          const session: AutomationSession = {
            session_id: crypto.randomUUID(),
            task_description: taskDescription,
            task_type: 'general' as TaskType,
            state: 'init' as AutomationState,
            ide: null,
            project_folder: null,
            task_details: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            metadata: {},
            execution_log: [],
          } as AutomationSession;
          set({ currentSession: session, sessions: [session, ...get().sessions] }, false, 'startAutomation');
          get()._saveSession();
          return `Automation session ${session.session_id} started`;
        },
        handleUserResponse: async (response: string) => {
          const sess = get().currentSession;
          if (!sess) return 'No active session';
          // Placeholder – just record the response in execution log
          const logEntry = {
            step: sess.execution_log.length + 1,
            action: `User response: ${response}`,
            status: 'completed' as const,
            timestamp: new Date().toISOString(),
          };
          sess.execution_log.push(logEntry);
          sess.updated_at = new Date().toISOString();
          set({ currentSession: { ...sess } }, false, 'handleUserResponse');
          get()._saveSession();
          return 'Response recorded';
        },
        getStatus: () => {
          const sess = get().currentSession;
          if (!sess) return null;
          return {
            sessionId: sess.session_id,
            state: sess.state,
            task: sess.task_description,
            type: sess.task_type,
            ide: sess.ide ?? null,
            folder: sess.project_folder ?? null,
          };
        },
        cancelAutomation: () => {
          const sess = get().currentSession;
          if (!sess) return 'No active session to cancel';
          sess.state = 'cancelled' as AutomationState;
          sess.updated_at = new Date().toISOString();
          set({ currentSession: { ...sess } }, false, 'cancelAutomation');
          get()._saveSession();
          return `Automation session ${sess.session_id} cancelled.`;
        },
        _saveSession: () => {
          const sess = get().currentSession;
          if (sess) {
            localStorage.setItem('jarvis-automation-session', JSON.stringify(sess));
          }
        },
      }),
      { name: 'jarvis-automation' }
    )
  )
);

// Selectors – retain existing names for compatibility
export const useCurrentSession = () => useAutomationStore((s) => s.currentSession);
export const useAutomationState = () => useAutomationStore((s) => s.currentSession?.state);
export const useIsExecuting = () => useAutomationStore((s) => false); // placeholder – not used in UI
export const useDetectedIDEs = () => useAutomationStore((s) => [] as any[]);
export const useScannedFolders = () => useAutomationStore((s) => [] as any[]);
