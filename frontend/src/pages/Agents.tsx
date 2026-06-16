import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Card } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ApiOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agents } from '../api/client';

interface AgentPreset {
  name: string;
  description: string;
  method: string;
  auth_type: string;
  api_base_url?: string;
  headers_template?: string;
  body_template: string;
}

const PRESETS: AgentPreset[] = [
  {
    name: 'OpenAI / DeepSeek (Chat)',
    description: 'OpenAI 兼容的聊天补全接口',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://api.deepseek.com/chat/completions',
    body_template: JSON.stringify({
      model: 'deepseek-chat',
      messages: [{ role: 'user', content: '{{input}}' }],
    }, null, 2),
  },
  {
    name: 'Dify 对话型应用',
    description: 'Dify Chatflow / Agent 应用的消息接口',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://dify.example.com/v1/chat-messages',
    body_template: JSON.stringify({
      inputs: {},
      query: '{{input}}',
      response_mode: 'blocking',
      conversation_id: '',
      user: 'test-user',
    }, null, 2),
  },
  {
    name: '通义千问 (Qwen)',
    description: '阿里云通义千问聊天补全',
    method: 'POST',
    auth_type: 'bearer',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
    body_template: JSON.stringify({
      model: 'qwen-plus',
      messages: [{ role: 'user', content: '{{input}}' }],
    }, null, 2),
  },
  {
    name: '自定义 JSON 回显',
    description: '发送简单 JSON 结构，用于调试连通性',
    method: 'POST',
    auth_type: 'none',
    body_template: JSON.stringify({
      input: '{{input}}',
      timestamp: '{{INPUT}}',
    }, null, 2),
  },
];

const Agents: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const [presetOpen, setPresetOpen] = useState(false);

  const { data, isLoading } = useQuery({ queryKey: ['agents'], queryFn: () => agents.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => editing ? agents.update(editing.id, d) : agents.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['agents'] }); message.success('保存成功'); setModalOpen(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => agents.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['agents'] }); message.success('已删除'); },
  });

  const handleCheck = async (id: string) => {
    const result = await agents.check(id);
    message.info(result.reachable ? '连通性正常' : `连接失败: ${result.error}`);
  };

  const applyPreset = (preset: AgentPreset) => {
    const fields: any = {
      method: preset.method,
      auth_type: preset.auth_type,
      body_template: preset.body_template,
      headers_template: preset.headers_template || form.getFieldValue('headers_template') || '',
    };
    if (preset.api_base_url) {
      fields.api_base_url = preset.api_base_url;
    }
    form.setFieldsValue(fields);
    message.success(`已应用预设: ${preset.name}`);
  };

  const openEdit = (record?: any) => {
    setEditing(record);
    const values = record ? { ...record } : { method: 'POST', auth_type: 'none', timeout_ms: 30000 };
    // Stringify JSON fields for the textarea inputs
    for (const field of ['body_template', 'headers_template']) {
      if (values[field] && typeof values[field] === 'object') {
        values[field] = JSON.stringify(values[field], null, 2);
      }
    }
    form.setFieldsValue(values);
    setModalOpen(true);
  };

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: 'API 地址', dataIndex: 'api_base_url', ellipsis: true },
    { title: '方法', dataIndex: 'method', width: 80 },
    { title: '认证', dataIndex: 'auth_type', width: 80 },
    { title: '状态', dataIndex: 'status', width: 80, render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag> },
    { title: '超时(ms)', dataIndex: 'timeout_ms', width: 100 },
    {
      title: '操作', width: 180,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<ApiOutlined />} onClick={() => handleCheck(r.id)}>检测</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="确定删除?" onConfirm={() => deleteMut.mutate(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>智能体管理</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>注册智能体</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title={editing ? '编辑智能体' : '注册智能体'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={640}>
        <Form form={form} layout="vertical" onFinish={(v) => {
          // Parse JSON string fields to objects
          const payload = { ...v };
          for (const field of ['body_template', 'headers_template']) {
            if (typeof payload[field] === 'string' && payload[field].trim()) {
              try { payload[field] = JSON.parse(payload[field]); }
              catch { message.error(`${field} 格式错误，请填写有效的 JSON`); return; }
            } else {
              delete payload[field];
            }
          }
          createMut.mutate(payload);
        }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="智能体名称" />
          </Form.Item>
          <Form.Item name="api_base_url" label="API 地址" rules={[{ required: true }]}>
            <Input placeholder="https://api.example.com/chat" />
          </Form.Item>
          <Form.Item name="method" label="请求方式"><Select options={[{ value: 'GET' }, { value: 'POST' }, { value: 'PUT' }]} /></Form.Item>
          <Form.Item name="auth_type" label="认证方式">
            <Select options={[{ value: 'none', label: '无' }, { value: 'bearer', label: 'Bearer Token' }, { value: 'api_key', label: 'API Key' }, { value: 'basic', label: 'Basic Auth' }]} />
          </Form.Item>
          <Form.Item name="auth_credentials" label="认证凭证"><Input.Password placeholder="API Key / Token" /></Form.Item>
          <Form.Item name="timeout_ms" label="超时阈值(ms)"><Input type="number" /></Form.Item>
          <Form.Item label="API 预设模板">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button icon={<ThunderboltOutlined />} onClick={() => setPresetOpen(true)}>
                选择预设模板...
              </Button>
              <span style={{ fontSize: 12, color: '#888' }}>预设将自动填充 API 地址、认证方式、请求体模板等信息</span>
            </Space>
          </Form.Item>
          <Form.Item name="headers_template" label="自定义请求头 (JSON)">
            <Input.TextArea rows={2} placeholder='{"Authorization": "Bearer ..."}' />
          </Form.Item>
          <Form.Item name="body_template" label="请求体模板 (JSON)">
            <Input.TextArea rows={4} placeholder={JSON.stringify({ messages: [{ role: 'user', content: '{{input}}' }] }, null, 2)} />
          </Form.Item>
        </Form>

        {/* Preset selection modal */}
        <Modal title="选择 API 预设模板" open={presetOpen} onCancel={() => setPresetOpen(false)}
          footer={null} width={520}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {PRESETS.map((p) => (
              <Card
                key={p.name}
                size="small"
                hoverable
                onClick={() => { applyPreset(p); setPresetOpen(false); }}
                style={{ cursor: 'pointer' }}
              >
                <Card.Meta
                  title={
                    <Space>
                      {p.name}
                      <Tag>{p.method}</Tag>
                      <Tag>{p.auth_type === 'none' ? '无认证' : p.auth_type}</Tag>
                    </Space>
                  }
                  description={
                    <div>
                      <div style={{ marginBottom: 4 }}>{p.description}</div>
                      {p.api_base_url && (
                        <code style={{ fontSize: 12, color: '#666' }}>{p.api_base_url}</code>
                      )}
                    </div>
                  }
                />
              </Card>
            ))}
          </Space>
        </Modal>
      </Modal>
    </div>
  );
};

export default Agents;
