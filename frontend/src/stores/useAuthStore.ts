import { create } from 'zustand';
import { persist, devtools } from 'zustand/middleware';

interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  providers: string[];
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (provider: 'github' | 'google') => Promise<void>;
  logout: () => void;
  setTokens: (access: string, refresh: string) => void;
  refreshAccessToken: () => Promise<void>;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,

        login: async (provider) => {
          set({ isLoading: true });
          const baseUrl = import.meta.env.VITE_API_URL || '';
          window.location.href = `${baseUrl}/oauth/authorize/${provider}`;
        },

        logout: () => {
          set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
          localStorage.removeItem('jarvis-access-token');
          localStorage.removeItem('jarvis-refresh-token');
        },

        setTokens: (access: string, refresh: string) => {
          localStorage.setItem('jarvis-access-token', access);
          localStorage.setItem('jarvis-refresh-token', refresh);
          set({ accessToken: access, refreshToken: refresh, isAuthenticated: true });
        },

        setUser: (user: User) => {
          set({ user });
        },

        refreshAccessToken: async () => {
          const refresh = localStorage.getItem('jarvis-refresh-token');
          if (!refresh) return;
          try {
            const baseUrl = import.meta.env.VITE_API_URL || '';
            const res = await fetch(`${baseUrl}/auth/refresh`, {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${refresh}` }
            });
            const { access_token } = await res.json();
            localStorage.setItem('jarvis-access-token', access_token);
            set({ accessToken: access_token });
          } catch {
            get().logout();
          }
        },
      }),
      { name: 'jarvis-auth' }
    )
  )
);