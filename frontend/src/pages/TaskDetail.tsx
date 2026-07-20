import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Table, Tag, Button, Typography, Progress, Space, Descriptions, Divider, message, Modal, Form, Input, Select, Rate } from 'antd';
import { ArrowLeftOutlined, PlayCircleOutlined, PauseCircleOutlined, StopOutlined, ReloadOutlined, AuditOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { tasks, agents, datasets, rules, aiJudges, annotations } from '../api/client';

const statusColors: Record<string, string> = {
  completed: 'success', running: 'processing', pending: 'default',
  paused: 'warning', failed: 'error', cancelled: 'default',
};

/* ─── Inline annotation display per task result ─── */
const ResultAnnotations: React.FC<{ taskResultId: string }> = ({ taskResultId }) => {
  const { data: annList } = useQuery({
    queryKey: ['annotations', taskResultId],
    queryFn: () => annotations.list({ task_result_id: taskResultId }),
    enabled: !!taskResultId,
    staleTime: 10_000,
  });

  if (!annList || annList.length === 0) return null;

  return (
    <div style={{ marginTop: 12, padding: '10px 14px', background: '#fffbe6', borderRadius: 6, border: '1px solid #ffe58f' }}>
      <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
        <AuditOutlined style={{ marginRight: 6 }} />审核信息
      </Typography.Text>
      {annList.map((ann: any) => (
        <div key={ann.id} style={{ padding: '6px 0', borderBottom: '1px solid #fff1b8' }}>
          <Space wrap>
            <Tag color={ann.status === 'approved' ? 'success' : ann.status === 'rejected' ? 'error' : 'processing'}>
              {ann.label || ann.status}
            </Tag>
            <span>评分: <b style={{ color: '#d46b08' }}>{ann.score}</b>/10</span>
            {ann.annotator && <span>审核人: {ann.annotator}</span>}
            <span style={{ fontSize: 12, color: '#999' }}>
              <ClockCircleOutlined style={{ marginRight: 4 }} />
              {ann.created_at ? new Date(ann.created_at).toLocaleString('zh-CN') : ''}
            </span>
          </Space>
          {ann.comment && (
            <div style={{ marginTop: 4, color: '#666', fontSize: 13, paddingLeft: 4 }}>
              {ann.comment}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const TaskDetail: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: task, isLoading, refetch } = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => tasks.get(taskId!),
    refetchInterval: (q) => q.state.data?.status === 'running' || q.state.data?.status === 'pending' ? 2000 : false,
  });

  const { data: summary } = useQuery({
    queryKey: ['task-summary', taskId],
    queryFn: () => tasks.summary(taskId!),
    enabled: !!taskId,
  });

  const { data: resultsData } = useQuery({
    queryKey: ['task-results', taskId],
    queryFn: () => tasks.results(taskId!, { size: 200 }),
    enabled: !!taskId,
  });

  const { data: taskWeights } = useQuery({
    queryKey: ['task-weights', taskId],
    queryFn: () => tasks.weights(taskId!),
    enabled: !!taskId,
  });

  const { data: agentsData } = useQuery({
    queryKey: ['agents-list'],
    queryFn: () => agents.list(),
    staleTime: 60_000,
  });

  const { data: datasetsData } = useQuery({
    queryKey: ['datasets-list'],
    queryFn: () => datasets.list(),
    staleTime: 60_000,
  });

  const { data: rulesData } = useQuery({
    queryKey: ['rules-list'],
    queryFn: () => rules.list(),
    staleTime: 60_000,
  });

  const { data: aiJudgesData } = useQuery({
    queryKey: ['ai-judges-list'],
    queryFn: () => aiJudges.list(),
    staleTime: 60_000,
  });

  const handleAction = async (action: string) => {
    try {
      if (action === 'start') await tasks.start(taskId!);
      else if (action === 'pause') await tasks.pause(taskId!);
      else if (action === 'cancel') await tasks.cancel(taskId!);
      message.success('操作成功');
      refetch();
      queryClient.invalidateQueries({ queryKey: ['task', taskId] });
    } catch (e: any) {
      message.error(`失败: ${e.message}`);
    }
  };

  const handleExport = async (format: string) => {
    try {
      const result = await tasks.report(taskId!, format);
      const blob = new Blob([typeof result === 'string' ? result : JSON.stringify(result)], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${taskId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch (e: any) {
      message.error(`导出失败: ${e.message}`);
    }
  };

  const [annotateResult, setAnnotateResult] = React.useState<any>(null);
  const [annotateOpen, setAnnotateOpen] = React.useState(false);
  const [annotateForm] = Form.useForm();

  const [expandedRowKeys, setExpandedRowKeys] = React.useState<string[]>([]);

  const toggleExpand = (rowId: string) => {
    setExpandedRowKeys(prev =>
      prev.includes(rowId) ? prev.filter(k => k !== rowId) : [...prev, rowId]
    );
  };

  const createAnnotationMut = useMutation({
    mutationFn: (d: any) => annotations.create(d),
    onSuccess: (_data, variables) => {
      message.success('审核已保存');
      setAnnotateOpen(false);
      queryClient.invalidateQueries({ queryKey: ['annotations'] });
      // Also invalidate results to show updated data
      if (variables.task_result_id) {
        queryClient.invalidateQueries({ queryKey: ['task-results', taskId] });
      }
    },
    onError: (e: any) => message.error(`审核失败: ${e.message}`),
  });

  const handleAnnotate = (result: any) => {
    setAnnotateResult(result);
    annotateForm.resetFields();
    setAnnotateOpen(true);
  };

  const submitAnnotation = () => {
    const values = annotateForm.getFieldsValue();
    createAnnotationMut.mutate({
      task_result_id: annotateResult.id,
      score: values.score,
      comment: values.comment,
      label: values.label || 'needs_review',
      status: 'approved',
    });
  };

  if (isLoading) return <Typography.Text>加载中...</Typography.Text>;
  if (!task) return <Typography.Text type="danger">任务不存在</Typography.Text>;

  const prog = task.progress || {};
  const percent = prog.total > 0 ? Math.round((prog.completed / prog.total) * 100) : 0;

  return (
    <div>
      <div className="page-header">
        <div className="flex items-center gap-8">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/tasks')}>返回</Button>
          <h1 style={{ margin: 0 }}>{task.name}</h1>
          <Tag color={statusColors[task.status]}>{task.status}</Tag>
        </div>
      </div>

      {(task.status === 'running' || task.status === 'pending') && (
        <Card className="mb-16">
          <Progress percent={percent} status="active" />
          <div className="text-center mt-8">
            {prog.completed || 0} / {prog.total || 0} 用例完成
          </div>
        </Card>
      )}

      <div className="stats-grid">
        <div className="stat-card"><div className="stat-label">总计</div><div className="stat-value">{summary?.total || 0}</div></div>
        <div className="stat-card"><div className="stat-label">通过</div><div className="stat-value" style={{ color: 'var(--success)' }}>{summary?.passed || 0}</div></div>
        <div className="stat-card"><div className="stat-label">失败</div><div className="stat-value" style={{ color: 'var(--danger)' }}>{summary?.failed || 0}</div></div>
        <div className="stat-card"><div className="stat-label">通过率</div><div className="stat-value">{((summary?.pass_rate || 0) * 100).toFixed(1)}%</div></div>
      </div>

      <Space style={{ marginBottom: 16 }}>
        {task.status === 'pending' && <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction('start')}>开始执行</Button>}
        {task.status === 'running' && <Button icon={<PauseCircleOutlined />} onClick={() => handleAction('pause')}>暂停</Button>}
        {task.status === 'paused' && <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction('start')}>恢复</Button>}
        {(task.status === 'running' || task.status === 'paused') && <Button danger icon={<StopOutlined />} onClick={() => handleAction('cancel')}>取消</Button>}
        {task.status === 'completed' && (
          <>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()}>刷新</Button>
            <Button onClick={() => handleExport('html')}>导出 HTML</Button>
            <Button onClick={() => handleExport('csv')}>导出 CSV</Button>
            <Button onClick={() => handleExport('md')}>导出 Markdown</Button>
          </>
        )}
      </Space>

      <Descriptions column={3} bordered size="small" className="mb-16">
        <Descriptions.Item label="任务ID"><Tag>{task.display_id || task.id.slice(0, 8)}</Tag></Descriptions.Item>
        <Descriptions.Item label="智能体">
          {(task.agent_ids || []).map((id: string) => {
            const a = (agentsData || []).find((x: any) => x.id === id);
            return a ? a.name : id;
          }).join(', ')}
        </Descriptions.Item>
        <Descriptions.Item label="数据集">
          {(task.dataset_ids || []).map((id: string) => {
            const d = (datasetsData || []).find((x: any) => x.id === id);
            return d ? d.name : id;
          }).join(', ')}
        </Descriptions.Item>
        <Descriptions.Item label="并发度">{task.config?.concurrency || '-'}</Descriptions.Item>
        <Descriptions.Item label="超时(ms)">{task.config?.timeout_ms || '-'}</Descriptions.Item>
        <Descriptions.Item label="全局通过线">{task.config?.global_threshold ?? '0.7'}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{new Date(task.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
        <Descriptions.Item label="状态"><Tag color={statusColors[task.status]}>{task.status}</Tag></Descriptions.Item>
        <Descriptions.Item label="评估规则">
          {(() => {
            const ids = task.config?.rule_ids || [];
            if (!ids.length) return '-';
            return ids.map((id: string) => {
              const r = (rulesData || []).find((x: any) => x.id === id);
              return r ? r.name : id;
            }).join(', ');
          })()}
        </Descriptions.Item>
        <Descriptions.Item label="AI 评估模型">
          {(() => {
            if (!task.ai_scoring_config || !Array.isArray(task.ai_scoring_config) || task.ai_scoring_config.length === 0) return '-';
            return task.ai_scoring_config.map((id: string) => {
              const j = (aiJudgesData || []).find((x: any) => x.id === id);
              return j ? `${j.name} (${j.model_name})` : id;
            }).join(', ');
          })()}
        </Descriptions.Item>
      </Descriptions>

      {taskWeights && taskWeights.length > 0 && (
        <Card size="small" title="评估维度权重与阈值" className="mb-16">
          {taskWeights.map((w: any) => (
            <Tag key={w.objective} className="mb-8" style={{ fontSize: 13, padding: '4px 10px' }}>
              {w.objective}: 权重={w.weight} 阈值={w.threshold ?? 0.7}
            </Tag>
          ))}
        </Card>
      )}

      <Typography.Title level={5}>执行结果</Typography.Title>
      <Table dataSource={resultsData?.items || []} rowKey="id" pagination={{ pageSize: 20 }}
        expandable={{
          expandedRowKeys,
          onExpand: (expanded, record) => {
            if (expanded) {
              setExpandedRowKeys(prev => [...prev, record.id]);
            } else {
              setExpandedRowKeys(prev => prev.filter(k => k !== record.id));
            }
          },
          expandedRowRender: (r: any) => (
            <div style={{ padding: 8 }}>
              <div style={{ textAlign: 'right', marginBottom: 8 }}>
                <Button size="small" icon={<AuditOutlined />} onClick={() => handleAnnotate(r)}>
                  审核
                </Button>
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={<Typography.Text strong>输入</Typography.Text>}>
                  <div style={{ whiteSpace: 'pre-wrap', maxHeight: 150, overflow: 'auto', background: '#fafafa', padding: 8, borderRadius: 4 }}>{r.raw_input || '-'}</div>
                </Descriptions.Item>
                <Descriptions.Item label={<Typography.Text strong>预期输出</Typography.Text>}>
                  <div style={{ whiteSpace: 'pre-wrap', maxHeight: 150, overflow: 'auto', background: '#fafafa', padding: 8, borderRadius: 4 }}>{r.expected_output || '-'}</div>
                </Descriptions.Item>
                <Descriptions.Item label={<Typography.Text strong>实际输出</Typography.Text>}>
                  <div style={{ whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto', background: '#f6ffed', padding: 8, borderRadius: 4 }}>
                    {r.display_output || '-'}
                    {r.raw_output && r.display_output !== r.raw_output && (
                      <details style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
                        <summary style={{ cursor: 'pointer' }}>查看原始响应</summary>
                        <pre style={{ marginTop: 4, padding: 8, background: '#f5f5f5', borderRadius: 4, maxHeight: 300, overflow: 'auto', fontSize: 11, whiteSpace: 'pre-wrap' }}>{r.raw_output}</pre>
                      </details>
                    )}
                  </div>
                </Descriptions.Item>
              </Descriptions>

              {r.scores && !r.scores.default && (
                <>
                  <Divider style={{ margin: '12px 0' }} />
                  <Typography.Text strong style={{ marginBottom: 8, display: 'block' }}>规则评分明细</Typography.Text>

                  {r.scores.rules && r.scores.rules.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>各规则评分</Typography.Text>
                      {r.scores.rules.map((rule: any, i: number) => (
                        <div key={i} style={{
                          display: 'flex', gap: 12, alignItems: 'center', padding: '4px 8px',
                          background: i % 2 === 0 ? '#fafafa' : 'white', borderRadius: 4, marginBottom: 2, fontSize: 13,
                        }}>
                          <Tag color={rule.passed ? 'success' : 'error'} style={{ marginRight: 0 }}>{rule.name || rule.rule_type}</Tag>
                          <span style={{ color: '#666', fontSize: 12 }}>({rule.rule_type})</span>
                          {rule.data_type === 'BOOLEAN' ? (
                            <span style={{ color: rule.passed ? '#3f8600' : '#cf1322', fontWeight: 600 }}>
                              {rule.passed ? '✅ PASS' : '❌ FAIL'}
                            </span>
                          ) : rule.data_type === 'CATEGORICAL' ? (
                            <Tag color="purple">{rule.details?.categorical_value || rule.score?.toFixed(2)}</Tag>
                          ) : (
                            <>
                              <span>得分: <b>{rule.score?.toFixed(2)}</b></span>
                              <span style={{ color: rule.passed ? '#3f8600' : '#cf1322', fontWeight: 600 }}>
                                {rule.passed ? 'PASS' : 'FAIL'}
                              </span>
                            </>
                          )}
                          {rule.error && <span style={{ color: '#cf1322', fontSize: 12 }}>错误: {rule.error}</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {r.scores.objectives && Object.keys(r.scores.objectives).length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>评估维度</Typography.Text>
                      <Descriptions column={4} size="small" bordered>
                        {Object.entries(r.scores.objectives).map(([name, data]: [string, any]) => (
                          <Descriptions.Item key={name} label={name}>
                            <span style={{ color: data.passed ? '#3f8600' : '#cf1322' }}>
                              {data.score.toFixed(2)} ({data.passed ? 'PASS' : 'FAIL'})
                            </span>
                            <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                              weight={data.weight} threshold={data.threshold ?? 0.7}
                            </Typography.Text>
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    </div>
                  )}
                </>
              )}
              <ResultAnnotations taskResultId={r.id} />
            </div>
          ),
          rowExpandable: () => true,
        }}
        columns={[
          { title: 'Case ID', dataIndex: 'case_id', width: 120 },
          { title: '通过', dataIndex: 'passed', width: 80, render: (v: boolean) => v ? <Tag color="success">PASS</Tag> : <Tag color="error">FAIL</Tag> },
          { title: '评分', dataIndex: 'total_score', width: 80, render: (v: number) => v?.toFixed(2) },
          { title: '响应(ms)', dataIndex: 'response_time_ms', width: 100, render: (v: number) => v ?? '-' },
          { title: '状态码', dataIndex: 'status_code', width: 80 },
          { title: '错误信息', dataIndex: 'error', ellipsis: true },
          {
            title: '详情', width: 80,
            render: (_: any, r: any) => (
              <Button size="small" type="link" onClick={() => toggleExpand(r.id)}>
                {expandedRowKeys.includes(r.id) ? '收起' : '展开'}
              </Button>
            ),
          },
        ]}
      />

      <Modal title="审核评测结果" open={annotateOpen} onCancel={() => setAnnotateOpen(false)}
        onOk={submitAnnotation} width={480}>
        <Form form={annotateForm} layout="vertical">
          <Form.Item name="score" label="审核评分(1-10)">
            <Rate count={10} tooltips={['1','2','3','4','5','6','7','8','9','10']} />
          </Form.Item>
          <Form.Item name="label" label="审核标签">
            <Select options={[
              { value: 'correct', label: '正确 (correct)' },
              { value: 'incorrect', label: '错误 (incorrect)' },
              { value: 'needs_review', label: '需复查 (needs_review)' },
            ]} />
          </Form.Item>
          <Form.Item name="comment" label="审核评语">
            <Input.TextArea rows={3} placeholder="对评测结果的人工审核意见" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TaskDetail;
