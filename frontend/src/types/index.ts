export interface Agent {
  id: string;
  name: string;
  api_base_url: string;
  method: string;
  auth_type: string;
  status: string;
  timeout_ms: number;
  created_at: string;
}

export interface Dataset {
  id: string;
  name: string;
  description?: string;
  dataset_type?: string;
  version: string;
  tags: string[];
  created_at: string;
}

export interface TestCase {
  id: string;
  case_id: string;
  input: string;
  expected_output?: string;
  categories: string[];
  objectives: string[];
  tags: string[];
}

export interface Rule {
  id: string;
  name: string;
  type: string;
  config: Record<string, any>;
  objectives: string[];
  weight: number;
  threshold: number;
  enabled: boolean;
  ai_judge_model_id?: string;
  ai_eval_prompt_id?: string;
  ai_rubric_id?: string;
}

export interface AIJudgeModel {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  api_base_url: string;
  status: string;
  parameters: Record<string, any>;
}

export interface Task {
  id: string;
  name: string;
  agent_ids: string[];
  dataset_ids: string[];
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  progress: { total: number; completed: number; failed: number; passed: number };
  config: Record<string, any>;
  created_at: string;
}

export interface TaskResult {
  id: string;
  task_id: string;
  agent_id: string;
  case_id: string;
  raw_output?: string;
  response_time_ms: number;
  status_code: number;
  error?: string;
  passed: boolean;
  total_score: number;
  scores: Record<string, any>;
}

export interface Space {
  id: string;
  name: string;
  description?: string;
  owner_id: string;
  created_at: string;
  updated_at?: string;
}

export interface User {
  id: string;
  username: string;
  email?: string;
  role: 'admin' | 'user';
  is_active: boolean;
  display_name?: string;
  space_id?: string;
  last_login?: string;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface DashboardStats {
  total_tasks: number;
  completed_tasks: number;
  running_tasks: number;
  total_agents: number;
  total_judges: number;
  total_datasets: number;
  recent_tasks: Task[];
}
