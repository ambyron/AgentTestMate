import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ApiOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aiJudges } from '../api/client';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google AI' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'custom', label: '自定义(兼容OpenAI)' },
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
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => aiJudges.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['ai-judges'] }); message.success('已删除'); },
  });

  const handleCheck = async (id: string) => {
    const result = await aiJudges.check(id);
    message.info(result.reachable ? '连通性正常' : `连接失败: ${result.error}`);
  };

  const openEdit = (record?: any) => {
    setEditing(record);
    form.setFieldsValue(record || { provider: 'openai', auth_type: 'api_key', parameters: { temperature: 0.0, max_tokens: 2048 } });
    setModalOpen(true);
  };

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
        onOk={() => form.submit()} width={640}>
        <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
          <Form.Item name="name" label="模型别名" rules={[{ required: true }]}><Input placeholder="GPT-4o 评估器" /></Form.Item>
          <Form.Item name="provider" label="提供商" rules={[{ required: true }]}><Select options={PROVIDERS} /></Form.Item>
          <Form.Item name="model_name" label="模型标识" rules={[{ required: true }]}><Input placeholder="gpt-4o / claude-sonnet-4-7" /></Form.Item>
          <Form.Item name="api_base_url" label="API 地址" rules={[{ required: true }]}><Input placeholder="https://api.openai.com/v1" /></Form.Item>
          <Form.Item name="auth_credentials" label="API Key"><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AIJudges;
