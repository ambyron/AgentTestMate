import React, { useState } from 'react';
import { Input, Button, Card, Typography, message } from 'antd';
import { RocketOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { spaces as spacesApi } from '../api/client';
import { useAuthStore } from '../stores/auth';

const { Title, Text } = Typography;

const SpaceSetup: React.FC = () => {
  const navigate = useNavigate();
  const { user, fetchMe } = useAuthStore();
  const [name, setName] = useState(user ? `${user.username} 的工作空间` : '我的工作空间');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) {
      message.error('请输入工作空间名称');
      return;
    }
    setLoading(true);
    try {
      await spacesApi.create({ name: name.trim(), description: description.trim() });
      await fetchMe();
      message.success('工作空间创建成功！');
      navigate('/');
    } catch (err: any) {
      if (err?.response?.status === 409) {
        await fetchMe();
        message.success('工作空间已存在');
        navigate('/');
        return;
      }
      message.error(err?.response?.data?.detail || '创建工作空间失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', background: '#f5f5f5',
    }}>
      <Card style={{ width: 480, borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,0.08)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 16,
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <RocketOutlined style={{ fontSize: 28, color: '#fff' }} />
          </div>
          <Title level={3} style={{ margin: 0 }}>创建工作空间</Title>
          <Text type="secondary">创建你的工作空间来管理智能体、数据集和评测任务</Text>
        </div>

        <div style={{ marginBottom: 16 }}>
          <Text strong>空间名称</Text>
          <Input
            size="large"
            placeholder="请输入工作空间名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ marginTop: 8 }}
          />
        </div>

        <div style={{ marginBottom: 24 }}>
          <Text strong>空间描述（可选）</Text>
          <Input.TextArea
            rows={3}
            placeholder="简要描述这个工作空间的用途"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{ marginTop: 8 }}
          />
        </div>

        <Button
          type="primary"
          size="large"
          block
          loading={loading}
          onClick={handleCreate}
          style={{ height: 44, borderRadius: 8 }}
        >
          创建工作空间
        </Button>
      </Card>
    </div>
  );
};

export default SpaceSetup;
