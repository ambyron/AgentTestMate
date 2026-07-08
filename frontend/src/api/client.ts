import axios from 'axios';

const client = axios.create({ baseURL: '/api/v1' });

// ── Auth interceptors ─────────────────────────────────────

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

// ── Auth API ──────────────────────────────────────────────

export const auth = {
  login: (username: string, password: string) =>
    client.post('/auth/login', { username, password }).then(r => r.data),
  me: () => client.get('/auth/me').then(r => r.data),
  changePassword: (old_password: string, new_password: string) =>
    client.put('/auth/change-password', { old_password, new_password }).then(r => r.data),
};

// ── Users API ─────────────────────────────────────────────

export const users = {
  list: (params?: any) => client.get('/users', { params }).then(r => r.data),
  get: (id: string) => client.get(`/users/${id}`).then(r => r.data),
  create: (data: any) => client.post('/users', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/users/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/users/${id}`),
  toggleActive: (id: string) => client.put(`/users/${id}/toggle-active`).then(r => r.data),
};

// Agent
export const agents = {
  list: (status?: string) => client.get('/agents', { params: { status } }).then(r => r.data),
  get: (id: string) => client.get(`/agents/${id}`).then(r => r.data),
  create: (data: any) => client.post('/agents', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/agents/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/agents/${id}`),
  check: (id: string) => client.post(`/agents/${id}/check`).then(r => r.data),
};

// Dataset
export const datasets = {
  list: (params?: any) => client.get('/datasets', { params }).then(r => r.data),
  get: (id: string) => client.get(`/datasets/${id}`).then(r => r.data),
  create: (data: any) => client.post('/datasets', data).then(r => r.data),
  import_: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return client.post('/datasets/import', fd).then(r => r.data);
  },
  update: (id: string, data: any) => client.put(`/datasets/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/datasets/${id}`),
};

// Rule
export const rules = {
  list: (params?: any) => client.get('/rules', { params }).then(r => r.data),
  get: (id: string) => client.get(`/rules/${id}`).then(r => r.data),
  create: (data: any) => client.post('/rules', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/rules/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/rules/${id}`),
  types: () => client.get('/rules/types').then(r => r.data),
  preview: (id: string, data: any) => client.post(`/rules/${id}/preview`, data).then(r => r.data),
  importRules: (data: any) => client.post('/rules/import', data).then(r => r.data),
};

// AI Judge
export const aiJudges = {
  list: (params?: any) => client.get('/ai-judges', { params }).then(r => r.data),
  get: (id: string) => client.get(`/ai-judges/${id}`).then(r => r.data),
  create: (data: any) => client.post('/ai-judges', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/ai-judges/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/ai-judges/${id}`),
  check: (id: string) => client.post(`/ai-judges/${id}/check`).then(r => r.data),
  previewScore: (data: any) => client.post('/ai-judges/preview-score', data).then(r => r.data),
};

// Task
export const tasks = {
  list: (params?: any) => client.get('/tasks', { params }).then(r => r.data),
  get: (id: string) => client.get(`/tasks/${id}`).then(r => r.data),
  create: (data: any) => client.post('/tasks', data).then(r => r.data),
  delete: (id: string) => client.delete(`/tasks/${id}`),
  start: (id: string) => client.post(`/tasks/${id}/start`).then(r => r.data),
  pause: (id: string) => client.post(`/tasks/${id}/pause`).then(r => r.data),
  resume: (id: string) => client.post(`/tasks/${id}/resume`).then(r => r.data),
  cancel: (id: string) => client.post(`/tasks/${id}/cancel`).then(r => r.data),
  rerun: (id: string) => client.post(`/tasks/${id}/rerun`).then(r => r.data),
  summary: (id: string) => client.get(`/tasks/${id}/summary`).then(r => r.data),
  results: (id: string, params?: any) => client.get(`/tasks/${id}/results`, { params }).then(r => r.data),
  report: (id: string, format: string) => client.get(`/tasks/${id}/report`, { params: { format } }).then(r => r.data),
  compare: (taskIds: string[]) => client.post('/tasks/compare', { task_ids: taskIds }).then(r => r.data),
  weights: (id: string) => client.get(`/tasks/${id}/weights`).then(r => r.data),
};

// ScoreConfig
export const scoreConfigs = {
  list: (params?: any) => client.get('/score-configs', { params }).then(r => r.data),
  get: (id: string) => client.get(`/score-configs/${id}`).then(r => r.data),
  create: (data: any) => client.post('/score-configs', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/score-configs/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/score-configs/${id}`),
};

// Annotation
export const annotations = {
  list: (params?: any) => client.get('/annotations', { params }).then(r => r.data),
  get: (id: string) => client.get(`/annotations/${id}`).then(r => r.data),
  create: (data: any) => client.post('/annotations', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/annotations/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/annotations/${id}`),
  judgeAccuracy: (judgeModelId?: string) => client.get('/annotations/judge-accuracy/stats', { params: { judge_model_id: judgeModelId } }).then(r => r.data),
};

// Eval Prompt
export const evalPrompts = {
  list: (params?: any) => client.get('/eval-prompts', { params }).then(r => r.data),
  get: (id: string) => client.get(`/eval-prompts/${id}`).then(r => r.data),
  create: (data: any) => client.post('/eval-prompts', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/eval-prompts/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/eval-prompts/${id}`),
  render: (id: string, data: any) => client.post(`/eval-prompts/${id}/render`, data).then(r => r.data),
  execute: (id: string, data: any) => client.post(`/eval-prompts/${id}/execute`, data).then(r => r.data),
  strategies: () => client.get('/eval-prompts/strategies/list').then(r => r.data),
};

// Scoring Rubric
export const rubrics = {
  list: (params?: any) => client.get('/rubrics', { params }).then(r => r.data),
  get: (id: string) => client.get(`/rubrics/${id}`).then(r => r.data),
  create: (data: any) => client.post('/rubrics', data).then(r => r.data),
};

// Objective
export const objectives = {
  list: () => client.get('/objectives').then(r => r.data),
  get: (id: string) => client.get(`/objectives/${id}`).then(r => r.data),
  create: (data: any) => client.post('/objectives', data).then(r => r.data),
  update: (id: string, data: any) => client.put(`/objectives/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/objectives/${id}`),
};

// Test Case
export const testCases = {
  get: (id: string) => client.get(`/test-cases/${id}`).then(r => r.data),
  update: (id: string, data: any) => client.put(`/test-cases/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/test-cases/${id}`),
};

// Space
export const spaces = {
  create: (data: any) => client.post('/spaces', data).then(r => r.data),
  getMy: () => client.get('/spaces/me').then(r => r.data),
  list: () => client.get('/spaces').then(r => r.data),
  get: (id: string) => client.get(`/spaces/${id}`).then(r => r.data),
};

// Dashboard
export const dashboard = {
  stats: () => client.get('/dashboard/stats').then(r => r.data),
};
