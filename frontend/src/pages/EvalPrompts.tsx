import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Tabs } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { evalPrompts, aiJudges } from '../api/client';

const STRATEGY_OPTIONS = [
  { value: 'simple', label: '通用评分 (Simple)' },
  { value: 'reference', label: '参照对比 (Reference)' },
  { value: 'rubric', label: '多维度评分 (Rubric)' },
  { value: 'chain_of_thought', label: '思维链评分 (Chain-of-Thought)' },
  { value: 'few_shot', label: '少样本评分 (Few-Shot)' },
  { value: 'pairwise', label: '对比选择 (Pairwise)' },
];

const EvalPrompts: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('system');
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({ queryKey: ['eval-prompts'], queryFn: () => evalPrompts.list() });
  const { data: judgesData } = useQuery({ queryKey: ['ai-judges-list'], queryFn: () => aiJudges.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => editing ? evalPrompts.update(editing.id, d) : evalPrompts.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['eval-prompts'] }); message.success('保存成功'); setModalOpen(false); },
    onError: (e: any) => message.error(`保存失败: ${e?.response?.data?.detail || e.message}`),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => evalPrompts.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['eval-prompts'] }); message.success('已删除'); },
  });

  const selectedStrategy = Form.useWatch('strategy', form);

  const openEdit = (record?: any) => {
    setEditing(record);
    const values = record ? { ...record } : { strategy: 'simple', output_format: 'json', version: '1.0' };
    if (values.few_shot_examples && typeof values.few_shot_examples === 'string') {
      try { values.few_shot_examples = JSON.parse(values.few_shot_examples); } catch { values.few_shot_examples = []; }
    }
    if (values.output_schema && typeof values.output_schema === 'string') {
      try { values.output_schema = JSON.parse(values.output_schema); } catch { values.output_schema = {}; }
    }
    form.setFieldsValue(values);
    setActiveTab('system');
    setModalOpen(true);
  };

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '策略', dataIndex: 'strategy', width: 160,
      render: (s: string) => {
        const opt = STRATEGY_OPTIONS.find(o => o.value === s);
        return <Tag>{opt?.label || s}</Tag>;
      },
    },
    { title: '版本', dataIndex: 'version', width: 80 },
    { title: '输出格式', dataIndex: 'output_format', width: 100 },
    { title: '内置', dataIndex: 'is_builtin', width: 60, render: (v: boolean) => v ? <Tag color="blue">是</Tag> : '-' },
    {
      title: '操作', width: 200,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<ExperimentOutlined />} onClick={() => navigate(`/eval-prompts/test?promptId=${r.id}`)}>测试</Button>
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
        <h1>评估提示词模板</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>新建模板</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title={editing ? '编辑提示词模板' : '新建提示词模板'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} confirmLoading={createMut.isPending} width={800}>
        <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}
          onFinishFailed={({ errorFields }) => {
            const names = errorFields.map(f => f.name.join('.'));
            message.warning(`请完善表单: ${names.join(', ')}`);
            // Switch to the tab containing the first error field
            const key = errorFields[0]?.name?.[0];
            if (key === 'user_prompt_template') setActiveTab('user');
          }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="strategy" label="评估策略" rules={[{ required: true }]}>
              <Select options={STRATEGY_OPTIONS} style={{ width: 240 }} />
            </Form.Item>
            <Form.Item name="version" label="版本"><Input style={{ width: 80 }} /></Form.Item>
            <Form.Item name="output_format" label="输出格式">
              <Select options={[
                { value: 'json', label: 'JSON' },
                { value: 'text', label: '纯文本' },
                { value: 'score_only', label: '仅分数' },
              ]} style={{ width: 120 }} />
            </Form.Item>
          </Space>

          <Tabs activeKey={activeTab} onChange={setActiveTab} defaultActiveKey="system">
            <Tabs.TabPane key="system" tab="System Prompt">
              <Form.Item name="system_prompt">
                <Input.TextArea rows={6} placeholder="系统级指令，定义 AI 裁判的角色和行为规范" />
              </Form.Item>
            </Tabs.TabPane>
            <Tabs.TabPane key="user" tab="User Prompt (Jinja2)">
              <Form.Item name="user_prompt_template" rules={[{ required: true }]}>
                <Input.TextArea rows={10} placeholder={'## Input\n{{input}}\n\n## Actual Output\n{{actual_output}}'} />
              </Form.Item>
            </Tabs.TabPane>
            <Tabs.TabPane key="schema" tab="输出 Schema (JSON)">
              <Form.Item name="output_schema">
                <Input.TextArea rows={6} placeholder='{"score": "number 0-1", "reasoning": "string"}' />
              </Form.Item>
            </Tabs.TabPane>
            <Tabs.TabPane key="fewshot" tab="Few-Shot 示例" disabled={selectedStrategy !== 'few_shot'}>
              <Form.Item name="few_shot_examples">
                <Input.TextArea rows={8} placeholder='[{"input": "...", "actual_output": "...", "score": 0.9, "reasoning": "..."}]' />
              </Form.Item>
            </Tabs.TabPane>
            <Tabs.TabPane key="tags" tab="标签">
              <Form.Item name="tags">
                <Select mode="tags" placeholder="输入标签后回车" />
              </Form.Item>
            </Tabs.TabPane>
          </Tabs>
        </Form>
      </Modal>
    </div>
  );
};

export default EvalPrompts;
