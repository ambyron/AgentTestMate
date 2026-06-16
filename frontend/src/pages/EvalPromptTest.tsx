import React, { useState, useEffect } from 'react';
import { Card, Form, Input, Select, Button, message, Typography, Space, Spin, Descriptions, Divider, Tag, Row, Col } from 'antd';
import { PlayCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { evalPrompts, aiJudges } from '../api/client';

const EvalPromptTest: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const promptIdFromUrl = searchParams.get('promptId');

  const [form] = Form.useForm();
  const [renderedPrompt, setRenderedPrompt] = useState('');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const { data: promptsData } = useQuery({ queryKey: ['eval-prompts'], queryFn: () => evalPrompts.list() });
  const { data: judgesData } = useQuery({ queryKey: ['ai-judges-list'], queryFn: () => aiJudges.list() });

  useEffect(() => {
    if (promptIdFromUrl && promptsData) {
      const found = (promptsData || []).find((p: any) => p.id === promptIdFromUrl);
      if (found) {
        form.setFieldsValue({
          prompt_id: found.id,
          strategy: found.strategy,
          input: '测试输入内容',
          expected_output: '预期的回复内容',
          actual_output: '智能体的实际回复内容',
        });
      }
    }
  }, [promptIdFromUrl, promptsData]);

  const handleRender = async () => {
    const values = form.getFieldsValue();
    if (!values.prompt_id) { message.warning('请选择提示词模板'); return; }
    setRenderedPrompt('');
    try {
      const resp = await evalPrompts.render(values.prompt_id, {
        strategy: values.strategy,
        input: values.input,
        expected_output: values.expected_output,
        actual_output: values.actual_output,
        rubric: values.rubric,
        criteria: values.criteria,
      });
      setRenderedPrompt(resp.rendered || '');
    } catch (e: any) {
      message.error(`渲染失败: ${e.message}`);
    }
  };

  const handleExecute = async () => {
    const values = form.getFieldsValue();
    if (!values.prompt_id) { message.warning('请选择提示词模板'); return; }
    if (!values.ai_judge_model_id) { message.warning('请选择 AI 评估模型'); return; }
    setLoading(true);
    setResult(null);
    try {
      const resp = await evalPrompts.execute(values.prompt_id, {
        ai_judge_model_id: values.ai_judge_model_id,
        strategy: values.strategy,
        input: values.input,
        expected_output: values.expected_output,
        actual_output: values.actual_output,
        rubric: values.rubric,
        criteria: values.criteria,
      });
      setResult(resp);
      if (!renderedPrompt) {
        setRenderedPrompt(resp.rendered_prompt || '');
      }
    } catch (e: any) {
      message.error(`执行失败: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const selectedPromptId = Form.useWatch('prompt_id', form);
  const selectedPrompt = (promptsData || []).find((p: any) => p.id === selectedPromptId);

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate('/eval-prompts')}>返回模板列表</Button>
        <Typography.Title level={4} style={{ margin: 0 }}>提示词测试工作台</Typography.Title>
      </Space>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="测试配置" size="small">
            <Form form={form} layout="vertical">
              <Form.Item name="prompt_id" label="提示词模板" rules={[{ required: true }]}>
                <Select placeholder="选择要测试的模板"
                  options={(promptsData || []).map((p: any) => ({ value: p.id, label: `${p.name} (${p.strategy})` }))} />
              </Form.Item>

              {selectedPrompt && (
                <div style={{ marginBottom: 12, fontSize: 13 }}>
                  <Typography.Text type="secondary">策略: </Typography.Text>
                  <Tag>{selectedPrompt.strategy}</Tag>
                  <Typography.Text type="secondary" style={{ marginLeft: 8 }}>版本: {selectedPrompt.version}</Typography.Text>
                </div>
              )}

              <Form.Item name="ai_judge_model_id" label="AI 评估模型">
                <Select placeholder="选择评估模型(执行评分时需要)"
                  allowClear
                  options={(judgesData || []).map((j: any) => ({ value: j.id, label: `${j.name} (${j.model_name})` }))} />
              </Form.Item>

              <Form.Item name="strategy" label="策略(覆盖)">
                <Select placeholder="覆盖模板默认策略" allowClear
                  options={[
                    { value: 'simple', label: '通用评分 (Simple)' },
                    { value: 'reference', label: '参照对比 (Reference)' },
                    { value: 'rubric', label: '多维度评分 (Rubric)' },
                    { value: 'chain_of_thought', label: '思维链评分 (CoT)' },
                    { value: 'few_shot', label: '少样本评分 (Few-Shot)' },
                    { value: 'pairwise', label: '对比选择 (Pairwise)' },
                  ]} />
              </Form.Item>

              <Form.Item name="input" label="输入" rules={[{ required: true }]}>
                <Input.TextArea rows={3} placeholder="测试输入内容" />
              </Form.Item>
              <Form.Item name="expected_output" label="预期输出">
                <Input.TextArea rows={3} placeholder="预期的回复内容(可选)" />
              </Form.Item>
              <Form.Item name="actual_output" label="实际输出" rules={[{ required: true }]}>
                <Input.TextArea rows={3} placeholder="智能体的实际回复内容" />
              </Form.Item>
              <Form.Item name="rubric" label="评分维度(Rubric)">
                <Input.TextArea rows={2} placeholder="多维度评分时填写评分维度描述" />
              </Form.Item>
              <Form.Item name="criteria" label="评分标准(Criteria)">
                <Input.TextArea rows={2} placeholder="评估标准的详细描述" />
              </Form.Item>

              <Space>
                <Button icon={<EyeOutlined />} onClick={handleRender}>渲染 Prompt</Button>
                <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={handleExecute}>执行评分</Button>
              </Space>
            </Form>
          </Card>
        </Col>

        <Col span={12}>
          <Card title="渲染结果" size="small" style={{ marginBottom: 16 }}>
            {renderedPrompt ? (
              <pre style={{
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                maxHeight: 400, overflow: 'auto',
                background: '#f5f5f5', padding: 12, borderRadius: 4,
                fontSize: 13,
              }}>{renderedPrompt}</pre>
            ) : (
              <Typography.Text type="secondary">点击"渲染 Prompt"查看渲染后的完整提示词</Typography.Text>
            )}
          </Card>

          <Card title="评分结果" size="small">
            {loading ? (
              <div style={{ textAlign: 'center', padding: 24 }}><Spin tip="AI 评估中..." /></div>
            ) : result ? (
              <div>
                <Descriptions column={2} size="small" bordered>
                  <Descriptions.Item label="评分">
                    <span style={{ fontSize: 18, fontWeight: 600, color: (result.score || 0) >= 0.7 ? '#3f8600' : '#cf1322' }}>
                      {result.score?.toFixed(4)}
                    </span>
                  </Descriptions.Item>
                  <Descriptions.Item label="延迟">{result.latency_ms?.toFixed(0)} ms</Descriptions.Item>
                </Descriptions>

                {result.reasoning && (
                  <>
                    <Divider style={{ margin: '12px 0' }} />
                    <Typography.Text strong>推理过程:</Typography.Text>
                    <div style={{
                      whiteSpace: 'pre-wrap', background: '#fafafa',
                      padding: 8, borderRadius: 4, marginTop: 4, fontSize: 13,
                    }}>
                      {result.reasoning}
                    </div>
                  </>
                )}
                {result.dimension_scores && Object.keys(result.dimension_scores).length > 0 && (
                  <>
                    <Divider style={{ margin: '12px 0' }} />
                    <Typography.Text strong>维度评分:</Typography.Text>
                    <Descriptions column={2} size="small" bordered style={{ marginTop: 4 }}>
                      {Object.entries(result.dimension_scores).map(([k, v]: [string, any]) => (
                        <Descriptions.Item key={k} label={k}>
                          {typeof v === 'number' ? v.toFixed(4) : String(v)}
                        </Descriptions.Item>
                      ))}
                    </Descriptions>
                  </>
                )}
                {result.error && (
                  <div style={{ marginTop: 8, color: '#cf1322' }}>
                    <Typography.Text type="danger">错误: {result.error}</Typography.Text>
                  </div>
                )}
              </div>
            ) : (
              <Typography.Text type="secondary">点击"执行评分"调用 AI 评估模型进行评分</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default EvalPromptTest;
