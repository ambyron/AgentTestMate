import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, InputNumber, Collapse } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ApiOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aiJudges } from '../api/client';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google AI' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'custom', label: '自定义(兼容OpenAI)' },
];

const AUTH_TYPES = [
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'api_key', label: 'API Key (Header)' },
  { value: 'none', label: '无认证' },
];

const PRESETS: { name: string; provider: string; api_base_url: string; auth_type: string; desc: string }[] = [
  { name: 'OpenAI GPT-4o', provider: 'openai', api_base_url: 'https://api.openai.com/v1', auth_type: 'bearer', desc: '互联网在线模型' },
  { name: 'Anthropic Claude', provider: 'anthropic', api_base_url: 'https://api.anthropic.com', auth_type: 'bearer', desc: '互联网在线模型' },
  { name: 'DeepSeek', provider: 'custom', api_base_url: 'https://api.deepseek.com/v1', auth_type: 'bearer', desc: '互联网在线模型' },
  { name: 'Ollama (本机)', provider: 'custom', api_base_url: 'http://localhost:11434/v1', auth_type: 'none', desc: '本机部署模型' },
  { name: 'vLLM (企业)', provider: 'custom', api_base_url: 'http://internal-api/v1', auth_type: 'basic', desc: '企业本地服务' },
];

const AIJudges: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: ['ai-judges'], queryFn: () => aiJudges.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => editing ? aiJudges.update(editing.id, d) : aiJudges.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ai-judges'] }); message.success('保存成功'); setModalOpen(false); },
    onError: (e: any) => message.error(`保存失败: ${e?.response?.data?.detail || e.message}`),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => aiJudges.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ai-judges'] }); message.success('已删除'); },
  });

  const handleCheck = async (id: string) => {
    try {
      const result = await aiJudges.check(id);
      message.info(result.reachable ? '✅ 连通性正常' : `❌ 连接失败: ${result.error}`);
    } catch (e: any) {
      message.error(`检测失败: ${e.message}`);
    }
  };

  const applyPreset = (preset: typeof PRESETS[0]) => {
    form.setFieldsValue({
      provider: preset.provider,
      api_base_url: preset.api_base_url,
      auth_type: preset.auth_type,
      model_name: form.getFieldValue('model_name') || '',
    });
    message.success(`已应用预设: ${preset.name}`);
  };

  const openEdit = (record?: any) => {
    setEditing(record);
    if (record) {
      const values = { ...record };
      if (values.headers_template && typeof values.headers_template === 'object') {
        values.headers_template = JSON.stringify(values.headers_template, null, 2);
      }
      if (values.parameters && typeof values.parameters === 'object') {
        // Keep as object for InputNumber fields
      }
      form.setFieldsValue(values);
    } else {
      form.resetFields();
      form.setFieldsValue({ provider: 'custom', auth_type: 'bearer', status: 'active' });
    }
    setModalOpen(true);
  };

  const watchedAuthType = Form.useWatch('auth_type', form);

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '提供商', dataIndex: 'provider', render: (p: string) => <Tag>{p}</Tag> },
    { title: '模型', dataIndex: 'model_name' },
    { title: 'API 地址', dataIndex: 'api_base_url', ellipsis: true },
    { title: '状态', dataIndex: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag> },
    {
      title: '操作', width: 200,
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
        <h1>AI 评估模型</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>注册评估模型</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title={editing ? '编辑 AI 评估模型' : '注册 AI 评估模型'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={700}>
        <Form form={form} layout="vertical" onFinish={(v) => {
          // Transform JSON string fields before submit
          if (v.headers_template && typeof v.headers_template === 'string') {
            try { v.headers_template = JSON.parse(v.headers_template); } catch { v.headers_template = {}; }
          }
          createMut.mutate(v);
        }}>
          {/* ─── 预设快速选择 ─── */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>快速预设：</div>
            <Space wrap size={4}>
              {PRESETS.map(p => (
                <Button key={p.name} size="small" icon={<ThunderboltOutlined />}
                  onClick={() => applyPreset(p)} style={{ fontSize: 12 }}>
                  {p.name}
                </Button>
              ))}
            </Space>
          </div>

          {/* ─── 基础信息 ─── */}
          <Form.Item name="name" label="模型别名" rules={[{ required: true }]}>
            <Input placeholder="如：GPT-4o 评估器" />
          </Form.Item>

          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="provider" label="提供商" rules={[{ required: true }]} style={{ width: 280 }}>
              <Select options={PROVIDERS} />
            </Form.Item>
            <Form.Item name="status" label="状态" initialValue="active" style={{ width: 120 }}>
              <Select options={[
                { value: 'active', label: '激活' },
                { value: 'inactive', label: '停用' },
              ]} />
            </Form.Item>
          </Space>

          {/* ─── 连接配置 ─── */}
          <div style={{ fontSize: 13, fontWeight: 600, color: '#333', marginBottom: 8, paddingTop: 4, borderTop: '1px solid var(--gray-200)' }}>
            连接配置
          </div>

          <Form.Item name="api_base_url" label="API 地址" rules={[{ required: true }]}>
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>

          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="model_name" label="模型标识" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input placeholder="gpt-4o / claude-sonnet-4" />
            </Form.Item>
            <Form.Item name="auth_type" label="认证方式" initialValue="bearer" style={{ width: 200 }}>
              <Select options={AUTH_TYPES} />
            </Form.Item>
          </Space>

          {watchedAuthType !== 'none' && (
            <Form.Item name="auth_credentials" label="认证凭据">
              <Input.Password placeholder={watchedAuthType === 'basic' ? 'username:password' : 'sk-...'} />
            </Form.Item>
          )}

          {/* ─── 高级配置 ─── */}
          <Collapse
            ghost
            items={[
              {
                key: 'advanced',
                label: <span style={{ fontSize: 13, color: '#888' }}>高级配置</span>,
                children: (
                  <>
                    <Form.Item name="headers_template" label="自定义请求头 (JSON)">
                      <Input.TextArea rows={3} placeholder='{"X-Gateway-Key": "your-key"}' />
                    </Form.Item>
                    <Space style={{ width: '100%' }} size={16}>
                      <Form.Item name={['parameters', 'temperature']} label="温度" initialValue={0.0}>
                        <InputNumber min={0} max={2} step={0.1} style={{ width: 120 }} />
                      </Form.Item>
                      <Form.Item name={['parameters', 'max_tokens']} label="最大 Token" initialValue={2048}>
                        <InputNumber min={64} max={32768} step={64} style={{ width: 140 }} />
                      </Form.Item>
                    </Space>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>
    </div>
  );
};

export default AIJudges;
