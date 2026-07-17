import React, { useState, useMemo } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, InputNumber, Collapse, Row, Col, Tabs, Card } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ApiOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aiJudges } from '../api/client';
import { JUDGE_PRESETS } from '../presets';
import RequestPreview from '../components/RequestPreview';

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

/* ─── 构建 Judge 请求预览 ─── */
function buildJudgeRequest(values: any) {
  const provider = values.provider || 'custom';
  const baseUrl = (values.api_base_url || '').replace(/\/+$/, '');
  const modelName = values.model_name || '';

  // 根据 provider 决定 API 路径
  let url = baseUrl;
  let method = 'POST';
  if (provider === 'anthropic') {
    url = `${baseUrl}/v1/messages`;
  } else if (provider === 'google') {
    url = `${baseUrl}/v1beta/models/${modelName}:generateContent`;
  } else {
    url = `${baseUrl}/chat/completions`;
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const authType = values.auth_type || 'bearer';
  const authCreds = values.auth_credentials || '';
  if (authType === 'bearer' && authCreds) {
    headers['Authorization'] = `Bearer ${authCreds.slice(0, 20)}…`;
  } else if (authType === 'basic' && authCreds) {
    headers['Authorization'] = `Basic ${authCreds.slice(0, 20)}…`;
  } else if (authType === 'api_key' && authCreds) {
    headers['Authorization'] = `Bearer ${authCreds.slice(0, 20)}…`;
  }

  // Custom headers
  if (values.headers_template) {
    try {
      const custom = typeof values.headers_template === 'string'
        ? JSON.parse(values.headers_template) : values.headers_template;
      Object.entries(custom).forEach(([k, v]) => { headers[k] = String(v); });
    } catch { /* ignore */ }
  }

  const params = values.parameters || {};
  const temperature = params.temperature ?? 0.0;
  const maxTokens = params.max_tokens ?? 2048;

  let body: any = {};
  if (provider === 'anthropic') {
    body = {
      model: modelName,
      max_tokens: maxTokens,
      messages: [{ role: 'user', content: '{{input}}' }],
    };
  } else if (provider === 'google') {
    body = {
      contents: [{ parts: [{ text: '{{input}}' }] }],
      generationConfig: { temperature, maxOutputTokens: maxTokens },
    };
  } else {
    // OpenAI 兼容
    body = {
      model: modelName,
      messages: [{ role: 'user', content: '{{input}}' }],
      temperature,
      max_tokens: maxTokens,
    };
  }

  return { method, url, headers, body };
}

const AIJudges: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const [presetOpen, setPresetOpen] = useState(false);
  const [presetCategory, setPresetCategory] = useState<string>('cloud');

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

  const applyPreset = (preset: typeof JUDGE_PRESETS[0]) => {
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
      form.setFieldsValue(values);
    } else {
      form.resetFields();
      form.setFieldsValue({ provider: 'custom', auth_type: 'bearer', status: 'active', parameters: { temperature: 0.0, max_tokens: 2048 } });
    }
    setModalOpen(true);
  };

  const watchedValues = Form.useWatch([], form);
  const requestPreview = useMemo(() => {
    if (!watchedValues) return { method: 'POST', url: '', headers: { 'Content-Type': 'application/json' }, body: {} };
    return buildJudgeRequest(watchedValues);
  }, [watchedValues]);

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
        onOk={() => form.submit()} width={960} footer={(_, { OkBtn, CancelBtn }) => (
          <Space>
            <Button icon={<ThunderboltOutlined />} onClick={() => setPresetOpen(true)}>选择预设</Button>
            <CancelBtn />
            <OkBtn />
          </Space>
        )}>
        <Form form={form} layout="vertical" onFinish={(v) => {
          if (v.headers_template && typeof v.headers_template === 'string') {
            try { v.headers_template = JSON.parse(v.headers_template); } catch { v.headers_template = {}; }
          }
          createMut.mutate(v);
        }}>
          <Row gutter={24}>
            {/* 左侧：配置字段 */}
            <Col span={14}>
              <Form.Item name="name" label="模型别名" rules={[{ required: true }]}>
                <Input placeholder="如：GPT-4o 评估器" />
              </Form.Item>

              <Space style={{ width: '100%' }} size={16}>
                <Form.Item name="provider" label="提供商" rules={[{ required: true }]} style={{ width: 200 }}>
                  <Select options={PROVIDERS} />
                </Form.Item>
                <Form.Item name="status" label="状态" initialValue="active" style={{ width: 120 }}>
                  <Select options={[
                    { value: 'active', label: '激活' },
                    { value: 'inactive', label: '停用' },
                  ]} />
                </Form.Item>
              </Space>

              <Form.Item name="api_base_url" label="API 地址" rules={[{ required: true }]}>
                <Input placeholder="https://api.openai.com/v1" />
              </Form.Item>

              <Space style={{ width: '100%' }} size={16}>
                <Form.Item name="model_name" label="模型标识" rules={[{ required: true }]} style={{ flex: 1 }}>
                  <Input placeholder="gpt-4o / deepseek-chat" />
                </Form.Item>
                <Form.Item name="auth_type" label="认证方式" initialValue="bearer" style={{ width: 180 }}>
                  <Select options={AUTH_TYPES} />
                </Form.Item>
              </Space>

              {watchedAuthType !== 'none' && (
                <Form.Item name="auth_credentials" label="认证凭据">
                  <Input.Password placeholder={watchedAuthType === 'basic' ? 'username:password' : 'sk-...'} />
                </Form.Item>
              )}

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
            </Col>

            {/* 右侧：请求预览 */}
            <Col span={10}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#333', marginBottom: 8 }}>请求预览</div>
              <RequestPreview
                method={requestPreview.method}
                url={requestPreview.url}
                headers={requestPreview.headers}
                body={requestPreview.body}
                height={520}
              />
            </Col>
          </Row>
        </Form>

        {/* 预设模板选择弹窗 */}
        <Modal title="选择评估模型预设" open={presetOpen} onCancel={() => setPresetOpen(false)}
          footer={null} width={520}>
          <Tabs
            activeKey={presetCategory}
            onChange={setPresetCategory}
            items={[
              { key: 'cloud', label: '互联网在线服务' },
              { key: 'local', label: '本地/私有化部署' },
            ]}
          />
          <Space direction="vertical" style={{ width: '100%' }}>
            {JUDGE_PRESETS.filter(p => p.category === presetCategory).map((p) => (
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
                      <Tag>{p.provider}</Tag>
                      <Tag>{p.auth_type === 'none' ? '无认证' : p.auth_type}</Tag>
                    </Space>
                  }
                  description={
                    <div>
                      <div style={{ marginBottom: 4 }}>{p.description}</div>
                      <code style={{ fontSize: 12, color: '#666' }}>{p.api_base_url}</code>
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

export default AIJudges;
