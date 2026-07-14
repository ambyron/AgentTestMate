import React, { useState, useMemo, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Select, Tag, Space, message, Popconfirm, Divider } from 'antd';
import { PlusOutlined, DeleteOutlined, PlayCircleOutlined, PauseCircleOutlined, StopOutlined, EyeOutlined, RedoOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { tasks, agents, datasets, rules, aiJudges } from '../api/client';

const statusColors: Record<string, string> = {
  completed: 'success', running: 'processing', pending: 'default',
  paused: 'warning', failed: 'error', cancelled: 'default',
};

const Tasks: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // Per-objective weight & threshold config, keyed by objective name
  const [objectiveConfigs, setObjectiveConfigs] = useState<Record<string, { weight: number; threshold: number }>>({});

  const { data, isLoading } = useQuery({ queryKey: ['tasks'], queryFn: () => tasks.list() });
  const { data: agentsData } = useQuery({ queryKey: ['agents-list'], queryFn: () => agents.list() });
  const { data: datasetsData } = useQuery({ queryKey: ['datasets-list'], queryFn: () => datasets.list() });
  const { data: rulesData } = useQuery({ queryKey: ['rules-list'], queryFn: () => rules.list() });
  const { data: aiJudgesData } = useQuery({ queryKey: ['ai-judges-list'], queryFn: () => aiJudges.list() });

  // Compute unique objectives from selected rules
  const watchedRuleIds = Form.useWatch('rule_ids', form);
  const selectedObjectives = useMemo(() => {
    const ruleIds = watchedRuleIds || [];
    if (!ruleIds.length || !rulesData) return [];
    const selectedRules = rulesData.filter((r: any) => ruleIds.includes(r.id));
    const objSet = new Set<string>();
    selectedRules.forEach((r: any) => (r.objectives || []).forEach((o: string) => objSet.add(o)));
    return Array.from(objSet);
  }, [watchedRuleIds, rulesData]);

  // Check if any selected rule is an AI-type rule
  const hasAiRule = useMemo(() => {
    const ruleIds = watchedRuleIds || [];
    if (!ruleIds.length || !rulesData) return false;
    return rulesData.some((r: any) => ruleIds.includes(r.id) && r.type.startsWith('llm_judge'));
  }, [watchedRuleIds, rulesData]);

  // Sync objectiveConfigs when selectedObjectives change
  useEffect(() => {
    setObjectiveConfigs(prev => {
      const next = { ...prev };
      selectedObjectives.forEach(obj => {
        if (!(obj in next)) next[obj] = { weight: 1.0, threshold: 0.7 };
      });
      // Remove configs for objectives no longer selected
      Object.keys(next).forEach(k => { if (!selectedObjectives.includes(k)) delete next[k]; });
      return next;
    });
  }, [selectedObjectives]);

  const createMut = useMutation({
    mutationFn: (d: any) => tasks.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tasks'] }); message.success('创建成功'); setModalOpen(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => tasks.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['tasks'] }); message.success('已删除'); },
  });

  const rerunMut = useMutation({
    mutationFn: (id: string) => tasks.rerun(id),
    onSuccess: (r: any) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      message.success(`已创建副本任务并开始执行: ${r.name}`);
      navigate(`/tasks/${r.task_id}`);
    },
    onError: (e: any) => message.error(`重新执行失败: ${e.message}`),
  });

  const handleAction = async (action: string, taskId: string) => {
    try {
      if (action === 'start') await tasks.start(taskId);
      else if (action === 'pause') await tasks.pause(taskId);
      else if (action === 'cancel') await tasks.cancel(taskId);
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      message.success('操作成功');
    } catch (e: any) {
      message.error(`操作失败: ${e.message}`);
    }
  };

  const columns = [
    { title: '任务名称', dataIndex: 'name', render: (n: string, r: any) => <a onClick={() => navigate(`/tasks/${r.id}`)}>{n}</a> },
    {
      title: '状态', dataIndex: 'status', render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag>,
    },
    {
      title: '进度', render: (_: any, r: any) => {
        const p = r.progress || {};
        return `${p.completed || 0}/${p.total || 0}`;
      },
    },
    { title: '创建时间', dataIndex: 'created_at', render: (t: string) => new Date(t).toLocaleString('zh-CN') },
    {
      title: '操作', width: 280,
      render: (_: any, r: any) => (
        <Space>
          {r.status === 'pending' && <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction('start', r.id)}>开始</Button>}
          {r.status === 'running' && <Button size="small" icon={<PauseCircleOutlined />} onClick={() => handleAction('pause', r.id)}>暂停</Button>}
          {r.status === 'paused' && <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction('start', r.id)}>恢复</Button>}
          {(r.status === 'running' || r.status === 'paused') && <Button size="small" danger icon={<StopOutlined />} onClick={() => handleAction('cancel', r.id)}>取消</Button>}
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/tasks/${r.id}`)}>详情</Button>
          {(r.status === 'completed' || r.status === 'failed' || r.status === 'cancelled') && <>
            <Button size="small" icon={<RedoOutlined />} onClick={() => rerunMut.mutate(r.id)}>重新执行</Button>
            <Popconfirm title="确定删除?" onConfirm={() => deleteMut.mutate(r.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>评测任务</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>新建任务</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title="新建评测任务" open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={640}>
        <Form form={form} layout="vertical" onFinish={(v) => {
          createMut.mutate({ ...v, objective_weights: objectiveConfigs });
        }}>
          <Form.Item name="name" label="任务名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="agent_ids" label="选择智能体" rules={[{ required: true }]}>
            <Select mode="multiple" placeholder="选择待测智能体"
              options={(agentsData || []).map((a: any) => ({ value: a.id, label: a.name }))} />
          </Form.Item>
          <Form.Item name="dataset_ids" label="选择评测数据集" rules={[{ required: true }]}>
            <Select mode="multiple" placeholder="选择数据集"
              options={(datasetsData || []).map((d: any) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item name="rule_ids" label="使用评估规则">
            <Select mode="multiple" placeholder="选择评估规则(可选，不选则使用所有已启用规则)"
              onChange={() => {
                // Force re-render of selectedObjectives on next tick
                setObjectiveConfigs(prev => ({ ...prev }));
              }}
              options={(rulesData || []).map((r: any) => ({ value: r.id, label: `${r.name} (${r.type})` }))} />
          </Form.Item>

          {selectedObjectives.length > 0 && (
            <>
              <Divider style={{ margin: '8px 0', fontSize: 13 }} plain>评估维度权重与阈值</Divider>
              <div style={{ background: '#fafafa', padding: '8px 12px', borderRadius: 6, marginBottom: 16 }}>
                {selectedObjectives.map(obj => {
                  const cfg = objectiveConfigs[obj] || { weight: 1.0, threshold: 0.7 };
                  return (
                    <Space key={obj} style={{ marginBottom: 6, width: '100%' }} align="baseline">
                      <Tag style={{ minWidth: 60, textAlign: 'center' }}>{obj}</Tag>
                      <span style={{ fontSize: 12, color: '#888' }}>权重</span>
                      <InputNumber size="small" min={0} max={10} step={0.1}
                        value={cfg.weight}
                        onChange={v => setObjectiveConfigs(prev => ({
                          ...prev, [obj]: { ...prev[obj], weight: v ?? 1.0 },
                        }))}
                        style={{ width: 80 }} />
                      <span style={{ fontSize: 12, color: '#888' }}>阈值</span>
                      <InputNumber size="small" min={0} max={1} step={0.05}
                        value={cfg.threshold}
                        onChange={v => setObjectiveConfigs(prev => ({
                          ...prev, [obj]: { ...prev[obj], threshold: v ?? 0.7 },
                        }))}
                        style={{ width: 80 }} />
                    </Space>
                  );
                })}
              </div>
            </>
          )}
          {hasAiRule && (
            <Form.Item name="ai_scoring_config" label="AI 评估模型">
              <Select mode="multiple" placeholder="选择 AI 评估模型(可选)"
                options={(aiJudgesData || []).map((j: any) => ({ value: j.id, label: `${j.name} (${j.model_name})` }))} />
            </Form.Item>
          )}
          <Space style={{ width: '100%' }} align="baseline" wrap>
            <Form.Item name="concurrency" label="并发度" initialValue={5}><InputNumber min={1} max={100} /></Form.Item>
            <Form.Item name="timeout_ms" label="超时(ms)" initialValue={30000}><InputNumber min={1000} max={600000} step={1000} /></Form.Item>
            <Form.Item name="global_threshold" label="全局通过线" initialValue={0.7}
              tooltip="整体评分达到此值才算案例通过">
              <InputNumber min={0} max={1} step={0.05} style={{ width: 100 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default Tasks;
