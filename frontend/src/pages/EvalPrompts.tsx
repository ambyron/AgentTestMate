import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Tabs, Descriptions, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ExperimentOutlined, EyeOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { evalPrompts } from '../api/client';

const STRATEGY_OPTIONS = [
  { value: 'simple', label: '通用评分 (Simple)' },
  { value: 'reference', label: '参照对比 (Reference)' },
  { value: 'rubric', label: '多维度评分 (Rubric)' },
  { value: 'chain_of_thought', label: '思维链评分 (Chain-of-Thought)' },
  { value: 'few_shot', label: '少样本评分 (Few-Shot)' },
  { value: 'pairwise', label: '对比选择 (Pairwise)' },
];

// Built-in template IDs per strategy (for auto-load)
const BUILTIN_IDS: Record<string, string> = {
  simple: 'builtin_simple',
  reference: 'builtin_reference',
  rubric: 'builtin_rubric',
  chain_of_thought: 'builtin_cot',
  few_shot: 'builtin_fewshot',
  pairwise: 'builtin_pairwise',
};

const EvalPrompts: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const [viewData, setViewData] = useState<any>(null);
  const [editing, setEditing] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('system');
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({ queryKey: ['eval-prompts'], queryFn: () => evalPrompts.list() });

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

  /* ─── Open edit/create modal ─── */
  const openEdit = (record?: any) => {
    setEditing(record);
    if (record) {
      const values = { ...record };
      if (values.few_shot_examples && typeof values.few_shot_examples === 'string') {
        try { values.few_shot_examples = JSON.parse(values.few_shot_examples); } catch { values.few_shot_examples = []; }
      }
      if (values.output_schema && typeof values.output_schema === 'string') {
        try { values.output_schema = JSON.parse(values.output_schema); } catch { values.output_schema = {}; }
      }
      form.setFieldsValue(values);
    } else {
      form.resetFields();
      form.setFieldsValue({ strategy: 'simple', output_format: 'json', version: '1.0' });
      // Auto-load built-in content for the default strategy
      setTimeout(() => handleStrategyChange('simple'), 100);
    }
    setActiveTab('system');
    setModalOpen(true);
  };

  /* ─── Open view modal (for built-in templates) ─── */
  const openView = (record: any) => {
    setViewData(record);
    setViewOpen(true);
  };

  /* ─── Auto-load builtin template content on strategy change ─── */
  const handleStrategyChange = (strategy: string) => {
    if (editing) return;  // Only for new templates
    const builtinId = BUILTIN_IDS[strategy];
    if (!builtinId || !data) return;
    const builtin = (data || []).find((t: any) => t.id === builtinId);
    if (!builtin) return;
    form.setFieldsValue({
      system_prompt: builtin.system_prompt || '',
      user_prompt_template: builtin.user_prompt_template || builtin.template_content || '',
      output_schema: builtin.output_schema || '',
      few_shot_examples: builtin.few_shot_examples || [],
      tags: builtin.tags || [],
    });
  };

  const columns = [
    { title: '#', dataIndex: 'seq', width: 60, sorter: (a: any, b: any) => (a.seq || 999) - (b.seq || 999) },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '策略', dataIndex: 'strategy', width: 160,
      render: (s: string) => {
        const opt = STRATEGY_OPTIONS.find(o => o.value === s);
        return <Tag>{opt?.label || s}</Tag>;
      },
    },
    { title: '版本', dataIndex: 'version', width: 80 },
    { title: '输出格式', dataIndex: 'output_format', width: 100 },
    {
      title: '类型', dataIndex: 'is_builtin', width: 80,
      render: (v: boolean) => v ? <Tag color="blue">内置</Tag> : <Tag color="green">自定义</Tag>,
    },
    {
      title: '操作', width: 220,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<ExperimentOutlined />} onClick={() => navigate(`/eval-prompts/test?promptId=${r.id}`)}>测试</Button>
          {r.is_builtin ? (
            <Button size="small" icon={<EyeOutlined />} onClick={() => openView(r)}>查看</Button>
          ) : (
            <>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
              <Popconfirm title="确定删除?" onConfirm={() => deleteMut.mutate(r.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </>
          )}
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
              <Select options={STRATEGY_OPTIONS} style={{ width: 240 }} onChange={handleStrategyChange} />
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

      {/* ─── View modal (for built-in templates) ─── */}
      <Modal title="查看提示词模板" open={viewOpen} onCancel={() => setViewOpen(false)}
        footer={<Button onClick={() => setViewOpen(false)}>关闭</Button>} width={800}>
        {viewData && (
          <div>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="名称">{viewData.name}</Descriptions.Item>
              <Descriptions.Item label="策略">
                {(() => { const opt = STRATEGY_OPTIONS.find(o => o.value === viewData.strategy); return opt?.label || viewData.strategy; })()}
              </Descriptions.Item>
              <Descriptions.Item label="版本">{viewData.version}</Descriptions.Item>
              <Descriptions.Item label="输出格式">{viewData.output_format}</Descriptions.Item>
              <Descriptions.Item label="类型" span={2}>
                <Tag color="blue">内置</Tag>
              </Descriptions.Item>
            </Descriptions>
            <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>System Prompt</Typography.Text>
            <div style={{ padding: 12, background: '#f6f8fa', borderRadius: 6, marginBottom: 16, whiteSpace: 'pre-wrap', fontSize: 13 }}>
              {viewData.system_prompt || '(无)'}
            </div>
            <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>User Prompt (Jinja2)</Typography.Text>
            <div style={{ padding: 12, background: '#f6f8fa', borderRadius: 6, whiteSpace: 'pre-wrap', fontSize: 13, maxHeight: 300, overflow: 'auto' }}>
              {viewData.user_prompt_template || viewData.template_content || '(无)'}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default EvalPrompts;
