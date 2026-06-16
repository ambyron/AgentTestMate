import React from 'react';
import { Table, Tag, Typography } from 'antd';
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { dashboard } from '../api/client';

const { Text } = Typography;

const statusColors: Record<string, string> = {
  completed: 'green',
  running: 'blue',
  pending: 'gold',
  paused: 'default',
  failed: 'red',
  cancelled: 'default',
};

const Dashboard: React.FC = () => {
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: dashboard.stats });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>仪表盘</h1>
          <div className="subtitle">系统运行概览</div>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">评测任务</div>
          <div className="stat-value">{data?.total_tasks || 0}</div>
          {data?.running_tasks ? (
            <div className="stat-footer"><span className="change up">↑</span> {data.running_tasks} 运行中</div>
          ) : null}
        </div>
        <div className="stat-card">
          <div className="stat-label">运行中</div>
          <div className="stat-value">{data?.running_tasks || 0}</div>
          <div className="stat-footer">
            <LoadingOutlined style={{ marginRight: 4 }} />
            进行中
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">智能体</div>
          <div className="stat-value">{data?.total_agents || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">数据集</div>
          <div className="stat-value">{data?.total_datasets || 0}</div>
        </div>
      </div>

      <div className="section-card">
        <div className="section-card-header">
          <h3>最近任务</h3>
        </div>
        <div className="section-card-body" style={{ padding: 0 }}>
          <Table
            dataSource={data?.recent_tasks || []}
            rowKey="id"
            pagination={false}
            loading={isLoading}
            columns={[
              {
                title: '任务名称', dataIndex: 'name',
                render: (n: any, r: any) => <Link to={`/tasks/${r.id}`} style={{ fontWeight: 500, color: 'var(--gray-800)' }}>{n}</Link>,
              },
              {
                title: '状态', dataIndex: 'status', width: 120,
                render: (s: string) => {
                  const color = statusColors[s] || 'default';
                  return <Tag color={color}>{s}</Tag>;
                },
              },
              {
                title: '创建时间', dataIndex: 'created_at', width: 180,
                render: (t: string) => <span className="text-sm text-muted">{new Date(t).toLocaleString('zh-CN')}</span>,
              },
            ]}
          />
        </div>
      </div>

      <div className="section-card mt-16">
        <div className="section-card-body flex items-center gap-8">
          <CheckCircleOutlined style={{ fontSize: 16, color: 'var(--gray-400)' }} />
          <span className="text-sm text-muted">
            已注册 AI 评估模型: <strong style={{ color: 'var(--gray-700)' }}>{data?.total_judges || 0}</strong>
          </span>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
