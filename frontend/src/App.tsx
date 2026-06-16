import React, { useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation, Link } from 'react-router-dom';
import {
  DashboardOutlined, RobotOutlined, DatabaseOutlined,
  CheckCircleOutlined, SlidersOutlined, FlagOutlined,
  ThunderboltOutlined, FileTextOutlined, BarChartOutlined,
  TeamOutlined, LogoutOutlined,
} from '@ant-design/icons';
import { Dropdown, Avatar, Spin, Breadcrumb } from 'antd';
import type { MenuProps } from 'antd';

import Dashboard from './pages/Dashboard';
import SpaceSetup from './pages/SpaceSetup';
import Agents from './pages/Agents';
import Datasets from './pages/Datasets';
import Rules from './pages/Rules';
import ScoreConfigs from './pages/ScoreConfigs';
import Objectives from './pages/Objectives';
import AIJudges from './pages/AIJudges';
import EvalPrompts from './pages/EvalPrompts';
import EvalPromptTest from './pages/EvalPromptTest';
import Tasks from './pages/Tasks';
import TaskDetail from './pages/TaskDetail';
import Login from './pages/Login';
import Users from './pages/Users';
import { useAuthStore } from './stores/auth';

/* ─── Navigation config ─── */
interface NavLeaf {
  key: string;
  label: string;
  icon: React.ReactNode;
}
interface NavGroup {
  label: string;
  items: NavLeaf[];
}
type NavEntry = NavLeaf | NavGroup;

function isGroup(e: NavEntry): e is NavGroup {
  return 'items' in e;
}

/* Derive sidebar active keys from pathname */
function isActive(pathname: string, key: string): boolean {
  if (key === '/') return pathname === '/';
  return pathname.startsWith(key);
}

/* ─── Breadcrumb builder ─── */
function getBreadcrumbItems(pathname: string) {
  const config: Record<string, { label: string; link?: string }[]> = {
    '/': [{ label: '仪表盘' }],
    '/agents': [{ label: '首页', link: '/' }, { label: '核心资源' }, { label: '智能体' }],
    '/datasets': [{ label: '首页', link: '/' }, { label: '核心资源' }, { label: '数据集' }],
    '/rules': [{ label: '首页', link: '/' }, { label: '评估' }, { label: '评估规则' }],
    '/rules/score-configs': [{ label: '首页', link: '/' }, { label: '评估' }, { label: '评分配置' }],
    '/rules/objectives': [{ label: '首页', link: '/' }, { label: '评估' }, { label: '目标配置' }],
    '/ai-judges': [{ label: '首页', link: '/' }, { label: '评估' }, { label: '评估模型' }],
    '/eval-prompts': [{ label: '首页', link: '/' }, { label: '评估' }, { label: '提示词模板' }],
    '/eval-prompts/test': [{ label: '首页', link: '/' }, { label: '评估' }, { label: '提示词测试' }],
    '/tasks': [{ label: '首页', link: '/' }, { label: '任务' }, { label: '评测任务' }],
    '/users': [{ label: '首页', link: '/' }, { label: '系统' }, { label: '用户管理' }],
    '/space-setup': [{ label: '创建工作空间' }],
  };

  if (config[pathname]) return config[pathname];

  if (pathname.startsWith('/tasks/')) {
    return [
      { label: '首页', link: '/' },
      { label: '任务', link: '/tasks' },
      { label: '任务详情' },
    ];
  }

  return [];
}

/* ─── Auth guard ─── */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/* ─── Space guard ─── */
function RequireSpace({ children }: { children: React.ReactNode }) {
  const { user, spaceId, initialized } = useAuthStore();
  // Wait for auth initialization before deciding where to redirect
  if (!initialized) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }
  // Admin bypasses space check
  if (user?.role === 'admin') {
    return <>{children}</>;
  }
  if (!spaceId) {
    return <Navigate to="/space-setup" replace />;
  }
  return <>{children}</>;
}

/* ─── Component ─── */
const App: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, initialize } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  // Refresh auth state on page load
  useEffect(() => {
    initialize();
  }, []);

  const renderNavItem = (leaf: NavLeaf) => {
    const active = isActive(location.pathname, leaf.key);
    return (
      <button
        key={leaf.key}
        className={`nav-item ${active ? 'active' : ''}`}
        onClick={() => navigate(leaf.key)}
      >
        <span className="nav-icon">{leaf.icon}</span>
        <span>{leaf.label}</span>
      </button>
    );
  };

  // Build nav entries conditionally
  const navEntries: NavEntry[] = [
    { key: '/', label: '仪表盘', icon: <DashboardOutlined /> },
    {
      label: '核心资源',
      items: [
        { key: '/agents', label: '智能体', icon: <RobotOutlined /> },
        { key: '/datasets', label: '数据集', icon: <DatabaseOutlined /> },
      ],
    },
    {
      label: '评估',
      items: [
        { key: '/rules', label: '评估规则', icon: <CheckCircleOutlined /> },
        { key: '/rules/score-configs', label: '评分配置', icon: <SlidersOutlined /> },
        { key: '/rules/objectives', label: '目标配置', icon: <FlagOutlined /> },
        { key: '/ai-judges', label: '评估模型', icon: <ThunderboltOutlined /> },
        { key: '/eval-prompts', label: '提示词模板', icon: <FileTextOutlined /> },
      ],
    },
    {
      label: '任务',
      items: [
        { key: '/tasks', label: '评测任务', icon: <BarChartOutlined /> },
      ],
    },
  ];

  // Admin-only nav entries
  if (isAdmin) {
    navEntries.push({
      label: '系统',
      items: [
        { key: '/users', label: '用户管理', icon: <TeamOutlined /> },
      ],
    });
  }

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'info',
      label: (
        <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>
          {user?.username} ({user?.role === 'admin' ? '管理员' : '用户'})
        </span>
      ),
      disabled: true,
    },
    { type: 'divider' },
    {
      key: 'logout',
      label: '退出登录',
      icon: <LogoutOutlined />,
      onClick: () => { logout(); navigate('/login'); },
    },
  ];

  // Login page — no shell
  if (location.pathname === '/login') {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
      </Routes>
    );
  }

  // Space setup page — standalone (no sidebar/header)
  if (location.pathname === '/space-setup') {
    return (
      <RequireAuth>
        <Routes>
          <Route path="/space-setup" element={<SpaceSetup />} />
        </Routes>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
      <RequireSpace>
      <div className="app-shell">
        {/* ─── Sidebar ─── */}
        <aside className="sidebar">
          <div className="sidebar-brand">
            <div className="sidebar-brand-inner">
              <div className="sidebar-logo">M</div>
              <span className="sidebar-brand-text">AgentTestMate</span>
            </div>
          </div>

          <nav className="sidebar-nav">
            {navEntries.map((entry) =>
              isGroup(entry) ? (
                <div key={entry.label} className="sidebar-nav-group">
                  <div className="sidebar-nav-label">{entry.label}</div>
                  {entry.items.map(renderNavItem)}
                </div>
              ) : (
                renderNavItem(entry)
              )
            )}
          </nav>

         
        </aside>

        {/* ─── Main ─── */}
        <div className="main-area">
          <header className="top-header">
            <Breadcrumb
              items={getBreadcrumbItems(location.pathname).map(item => ({
                title: item.link
                  ? <Link to={item.link}>{item.label}</Link>
                  : <span style={{ fontWeight: 600, color: 'var(--gray-700)' }}>{item.label}</span>,
              }))}
            />
            <div className="header-actions">
              {user?.role !== 'admin' && user?.space_id && (
                <span style={{
                  fontSize: 12, color: 'var(--gray-400)', marginRight: 12,
                  background: 'var(--gray-100)', padding: '2px 10px', borderRadius: 4,
                }}>
                  {user.username} 的工作空间
                </span>
              )}

              <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                <div style={{
                  width: 30, height: 30, borderRadius: 6,
                  background: 'var(--gray-200)', border: 'none', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: 'var(--gray-500)', fontSize: 13, fontWeight: 600,
                }}>
                  {user?.username?.charAt(0).toUpperCase() || 'U'}
                </div>
              </Dropdown>
            </div>
          </header>

          <div className="page-content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/datasets" element={<Datasets />} />
              <Route path="/rules" element={<Rules />} />
              <Route path="/rules/score-configs" element={<ScoreConfigs />} />
              <Route path="/rules/objectives" element={<Objectives />} />
              <Route path="/ai-judges" element={<AIJudges />} />
              <Route path="/eval-prompts" element={<EvalPrompts />} />
              <Route path="/eval-prompts/test" element={<EvalPromptTest />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/tasks/:taskId" element={<TaskDetail />} />
              {isAdmin && <Route path="/users" element={<Users />} />}
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </div>
        </div>
      </div>
      </RequireSpace>
    </RequireAuth>
  );
};

export default App;
