import React, { useState, useMemo } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Card, Row, Col, Tabs } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ApiOutlined, ThunderboltOutlined, CopyOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agents } from '../api/client';
import { AGENT_PRESETS } from '../presets';
import RequestPreview from '../components/RequestPreview';

/* ─── 构建请求预览 ─── */
function buildRequest(values: any) {
  const method = values.method || 'POST';
  const url = values.api_base_url || '';

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const authType = values.auth_type || 'none';
  const authCreds = values.auth_credentials || '';
  if (authType === 'bearer' && authCreds) {
    headers['Authorization'] = `Bearer ${authCreds.slice(0, 20)}…`;
  } else if (authType === 'api_key' && authCreds) {
    headers['Authorization'] = `Bearer ${authCreds.slice(0, 20)}…`;
  } else if (authType === 'basic' && authCreds) {
    headers['Authorization'] = `Basic ${authCreds.slice(0, 20)}…`;
  }
  // Custom headers
  if (values.headers_template) {
    try {
      const custom = typeof values.headers_template === 'string'
        ? JSON.parse(values.headers_template) : values.headers_template;
      Object.entries(custom).forEach(([k, v]) => { headers[k] = String(v); });
    } catch { /* ignore */ }
  }

  let body: any = {};
  if (values.body_template) {
    try {
      body = typeof values.body_template === 'string'
        ? JSON.parse(values.body_template) : values.body_template;
    } catch { body = { _parseError: 'JSON 格式错误' }; }
  }

  return { method, url, headers, body };
}

const Agents: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const [presetOpen, setPresetOpen] = useState(false);
  const [presetCategory, setPresetCategory] = useState<string>('cloud');

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

  const applyPreset = (preset: typeof AGENT_PRESETS[0]) => {
    const fields: any = {
      method: preset.method,
      auth_type: preset.auth_type,
      body_template: preset.body_template,
      api_base_url: preset.api_base_url,
      headers_template: preset.headers_template || form.getFieldValue('headers_template') || '',
    };
    form.setFieldsValue(fields);
    message.success(`已应用预设: ${preset.name}`);
  };

  const openEdit = (record?: any) => {
    setEditing(record);
    const values = record ? { ...record } : { method: 'POST', auth_type: 'none', timeout_ms: 30000 };
    for (const field of ['body_template', 'headers_template']) {
      if (values[field] && typeof values[field] === 'object') {
        values[field] = JSON.stringify(values[field], null, 2);
      }
    }
    form.setFieldsValue(values);
    setModalOpen(true);
  };

  const watchedValues = Form.useWatch([], form);
  const requestPreview = useMemo(() => {
    if (!watchedValues) return { method: 'POST', url: '', headers: { 'Content-Type': 'application/json' }, body: {} };
    return buildRequest(watchedValues);
  }, [watchedValues]);

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
        onOk={() => form.submit()} width={960} footer={(_, { OkBtn, CancelBtn }) => (
          <Space>
            <Button icon={<ThunderboltOutlined />} onClick={() => setPresetOpen(true)}>选择预设模板</Button>
            <CancelBtn />
            <OkBtn />
          </Space>
        )}>
        <Form form={form} layout="vertical" onFinish={(v) => {
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
          <Row gutter={24}>
            {/* 左侧：配置字段 */}
            <Col span={14}>
              <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                <Input placeholder="智能体名称" />
              </Form.Item>
              <Form.Item name="api_base_url" label="API 地址" rules={[{ required: true }]}>
                <Input placeholder="https://api.example.com/chat/completions" />
              </Form.Item>
              <Space style={{ width: '100%' }} size={16}>
                <Form.Item name="method" label="请求方式" style={{ width: 140 }}>
                  <Select options={[{ value: 'GET' }, { value: 'POST' }, { value: 'PUT' }]} />
                </Form.Item>
                <Form.Item name="auth_type" label="认证方式" style={{ width: 180 }}>
                  <Select options={[
                    { value: 'none', label: '无认证' },
                    { value: 'bearer', label: 'Bearer Token' },
                    { value: 'api_key', label: 'API Key' },
                    { value: 'basic', label: 'Basic Auth' },
                  ]} />
                </Form.Item>
                <Form.Item name="timeout_ms" label="超时(ms)" style={{ width: 120 }}>
                  <Input type="number" placeholder="30000" />
                </Form.Item>
              </Space>
              <Form.Item name="auth_credentials" label="认证凭证">
                <Input.Password placeholder="API Key / Token" />
              </Form.Item>
              <Form.Item name="headers_template" label="自定义请求头 (JSON)">
                <Input.TextArea rows={2} placeholder='{"X-Custom-Header": "value"}' />
              </Form.Item>
              <Form.Item name="body_template" label="请求体模板 (JSON)" rules={[{ required: true }]}>
                <Input.TextArea rows={7} placeholder={JSON.stringify({
                  model: 'deepseek-chat',
                  messages: [{ role: 'user', content: '{{input}}' }],
                }, null, 2)} />
              </Form.Item>
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
        <Modal title="选择 API 预设模板" open={presetOpen} onCancel={() => setPresetOpen(false)}
          footer={null} width={640}>
          <Tabs
            activeKey={presetCategory}
            onChange={setPresetCategory}
            items={[
              { key: 'cloud', label: '互联网在线服务' },
              { key: 'local', label: '本地/私有化部署' },
              { key: 'other', label: '其他' },
            ]}
          />
          <Space direction="vertical" style={{ width: '100%' }}>
            {AGENT_PRESETS.filter(p => p.category === presetCategory).map((p) => (
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
                      <code style={{ fontSize: 12, color: '#666' }}>{p.api_base_url}</code>
                      {p.hint && <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>{p.hint}</div>}
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
