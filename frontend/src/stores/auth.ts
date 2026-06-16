import { create } from 'zustand';
import { auth as authApi } from '../api/client';
import type { User } from '../types';

interface AuthState {
  token: string | null;
  user: User | null;
  spaceId: string | null;
  loading: boolean;
  initialized: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  initialize: () => Promise<void>;
  fetchMe: () => Promise<void>;
  checkAuth: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('auth_token'),
  user: (() => {
    try {
      const raw = localStorage.getItem('auth_user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })(),
  spaceId: (() => {
    try {
      const raw = localStorage.getItem('auth_user');
      if (raw) {
        const u = JSON.parse(raw);
        return u.space_id || null;
      }
      return null;
    } catch {
      return null;
    }
  })(),
  loading: false,
  initialized: false,
  isAuthenticated: !!localStorage.getItem('auth_token'),

  login: async (username: string, password: string) => {
    set({ loading: true });
    try {
      const result = await authApi.login(username, password);
      localStorage.setItem('auth_token', result.access_token);
      localStorage.setItem('auth_user', JSON.stringify(result.user));
      set({
        token: result.access_token,
        user: result.user,
        spaceId: result.user.space_id || null,
        isAuthenticated: true,
        loading: false,
      });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    set({ token: null, user: null, spaceId: null, isAuthenticated: false });
  },

  initialize: async () => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      set({ initialized: true });
      return;
    }
    try {
      const user = await authApi.me();
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user, isAuthenticated: true, spaceId: user.space_id || null, initialized: true });
    } catch {
      set({ initialized: true });
    }
  },

  fetchMe: async () => {
    try {
      const user = await authApi.me();
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user, isAuthenticated: true, spaceId: user.space_id || null });
    } catch {
      get().logout();
    }
  },

  checkAuth: () => {
    const { isAuthenticated } = get();
    if (!isAuthenticated) {
      window.location.href = '/login';
      return false;
    }
    return true;
  },
}));
