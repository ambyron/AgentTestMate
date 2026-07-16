import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Switch, Space, message, Typography, Tag, Popconfirm, Upload } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, ExperimentOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rules, evalPrompts, rubrics, objectives as objectivesApi } from '../api/client';

const RULE_TYPES = [
  { value: 'exact_match', label: '精确匹配', category: 'builtin' },
  { value: 'keyword', label: '关键词匹配', category: 'builtin' },
  { value: 'regex', label: '正则匹配', category: 'builtin' },
  { value: 'duration', label: '响应时间', category: 'builtin' },
  { value: 'length', label: '长度约束', category: 'builtin' },
  { value: 'llm_judge', label: 'AI 模型评分', category: 'ai' },
];

const AI_RULE_TYPES = ['llm_judge'];

/* ─── Rule type → scoring data type mapping ─── */
const RULE_DATA_TYPES: Record<string, { label: string; color: string }> = {
  exact_match: { label: 'NUMERIC → BOOLEAN', color: 'green' },
  keyword: { label: 'NUMERIC', color: 'blue' },
  regex: { label: 'BOOLEAN', color: 'green' },
  duration: { label: 'BOOLEAN', color: 'green' },
  length: { label: 'BOOLEAN', color: 'green' },
  llm_judge: { label: 'NUMERIC', color: 'blue' },
};


/* ─── Config templates per rule type ─── */
interface ConfigTemplate {
  template: string;
  description: string;
}

const CONFIG_TEMPLATES: Record<string, ConfigTemplate> = {
  exact_match: {
    template: JSON.stringify({ case_sensitive: true }, null, 2),
    description: 'case_sensitive (bool): 是否区分大小写，不区分时 "ABC" 与 "abc" 视为相等',
  },
  keyword: {
    template: JSON.stringify({ include: [], exclude: [] }, null, 2),
    description:
      'include (string[]): 输出必须包含的关键词列表\n'
        + 'exclude (string[]): 输出中不能出现的词语\n'
        + '【注意】include 为空时，自动从期望输出中提取有意义的词语（英文单词、中文双字词、数字）作为匹配关键词',
  },
  regex: {
    template: JSON.stringify({ pattern: '', match_type: 'search' }, null, 2),
    description:
      'pattern (string): 正则表达式\n'
        + 'match_type (string): 匹配方式 — search(搜索) / match(开头匹配) / fullmatch(完全匹配)',
  },
  duration: {
    template: JSON.stringify({ min_ms: 0, max_ms: 30000 }, null, 2),
    description: 'min_ms (number): 最小响应时间(毫秒)\nmax_ms (number): 最大响应时间(毫秒)',
  },
  length: {
    template: JSON.stringify({ min_chars: 0, max_chars: 10000 }, null, 2),
    description: 'min_chars (number): 最小字符数\nmax_chars (number): 最大字符数',
  },
  llm_judge: {
    template: JSON.stringify({ criteria: '' }, null, 2),
    description: 'criteria (string): AI 评分准则，描述期望从哪些维度评估回复质量',
  },
};

const Rules: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: ['rules'], queryFn: () => rules.list() });
  const { data: evalPromptsData } = useQuery({ queryKey: ['eval-prompts-list'], queryFn: () => evalPrompts.list() });
  const { data: rubricsData } = useQuery({ queryKey: ['rubrics-list'], queryFn: () => rubrics.list() });
  const { data: objectivesData } = useQuery({ queryKey: ['objectives'], queryFn: () => objectivesApi.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => editing ? rules.update(editing.id, d) : rules.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['rules'] }); message.success('保存成功'); setModalOpen(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => rules.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['rules'] }); message.success('已删除'); },
  });

  const handlePreview = async (ruleId: string) => {
    setPreviewResult({ loading: true });
    setPreviewOpen(true);
    try {
      const result = await rules.preview(ruleId, {
        input: '测试输入内容',
        actual_output: '智能体的实际回复内容',
        expected_output: '期望的回复内容',
      });
      setPreviewResult(result);
    } catch {
      setPreviewResult({ error: '预览失败' });
    }
  };

  const openEdit = (record?: any) => {
    setEditing(record);
    if (record) {
      const values = { ...record };
      if (values.config && typeof values.config === 'object') {
        values.config = JSON.stringify(values.config, null, 2);
      }
      // Transform ai_eval_prompt_id → rating_method
      if (values.ai_eval_prompt_id) {
        values.rating_method = `tpl_${values.ai_eval_prompt_id}`;
      }
      delete values.ai_eval_prompt_id;
      delete values.eval_strategy;
      form.setFieldsValue(values);
    } else {
      // New rule: all fields empty
      form.resetFields();
    }
    setModalOpen(true);
  };

  /* ─── Auto-fill config template when rule type changes ─── */
  const handleTypeChange = (type: string) => {
    const tpl = CONFIG_TEMPLATES[type];
    if (tpl && !editing) {
      // Only auto-fill for new rules
      form.setFieldValue('config', tpl.template);
    }
  };

  const selectedType = Form.useWatch('type', form);
  const isAiType = selectedType && AI_RULE_TYPES.includes(selectedType);
  const currentConfig = selectedType ? CONFIG_TEMPLATES[selectedType] : null;

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '名称', dataIndex: 'name' },
    { title: '规则类型', dataIndex: 'type', render: (t: string) => { const lt = RULE_TYPES.find(r => r.value === t); return <Tag>{lt?.label || t}</Tag>; } },
    { title: '打分类型', dataIndex: 'type', width: 130,
      render: (t: string) => { const dt = RULE_DATA_TYPES[t]; return dt ? <Tag color={dt.color}>{dt.label}</Tag> : '-'; } },
    { title: '阈值', dataIndex: 'threshold', width: 80 },
    { title: '评价目标', dataIndex: 'objectives', width: 200,
      render: (obj: string[]) => obj?.length ? obj.map(o => <Tag key={o}>{o}</Tag>) : '-' },
    { title: '启用', dataIndex: 'enabled', width: 60, render: (v: boolean) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    {
      title: '操作', width: 200,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<ExperimentOutlined />} onClick={() => handlePreview(r.id)}>预览</Button>
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
        <h1>评估规则</h1>
        <div className="page-header-actions">
          <Button icon={<UploadOutlined />} onClick={() => { setImportOpen(true); setImportResult(null); }}>导入规则</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>新建规则</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title={editing ? '编辑规则' : '新建规则'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={720}>
        <Form form={form} layout="vertical" onFinish={(v) => {
          console.log('[DEBUG] 提交的表单数据:', JSON.stringify(v, null, 2));
          // Transform rating_method → ai_eval_prompt_id
          if (v.rating_method && v.rating_method.startsWith('tpl_')) {
            v.ai_eval_prompt_id = v.rating_method.replace('tpl_', '');
          }
          delete v.eval_strategy;
          delete v.rating_method;
          console.log('[DEBUG] 转换后的提交数据:', JSON.stringify(v, null, 2));
          createMut.mutate(v);
        }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="规则的作用和适用场景说明" />
          </Form.Item>
          <Form.Item name="type" label="规则类型" rules={[{ required: true }]}>
            <Select options={RULE_TYPES} onChange={handleTypeChange} placeholder="请选择规则类型" />
          </Form.Item>

          {selectedType && (() => {
            const dt = RULE_DATA_TYPES[selectedType];
            return dt ? (
              <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6, fontSize: 13 }}>
                <span style={{ color: '#555' }}>打分类型: </span>
                <Tag color={dt.color}>{dt.label}</Tag>
              </div>
            ) : null;
          })()}

          {/* AI Judge fields - only visible for AI rule types */}
          {isAiType && (
            <>
              {(() => {
                // Build template options grouped by type, sorted by seq
                const builtinPrompts = (evalPromptsData || [])
                  .filter((p: any) => p.is_builtin)
                  .sort((a: any, b: any) => (a.seq || 99) - (b.seq || 99));
                const customPrompts = (evalPromptsData || [])
                  .filter((p: any) => !p.is_builtin)
                  .sort((a: any, b: any) => (a.seq || 999) - (b.seq || 999));
                const options: any[] = [];
                if (builtinPrompts.length > 0) {
                  options.push({
                    label: '🔵 默认模板',
                    options: builtinPrompts.map((p: any) => ({
                      value: `tpl_${p.id}`,
                      label: `#${p.seq} ${p.name} (${p.strategy})`,
                    })),
                  });
                }
                if (customPrompts.length > 0) {
                  options.push({
                    label: '🟢 自定义模板',
                    options: customPrompts.map((p: any) => ({
                      value: `tpl_${p.id}`,
                      label: `#${p.seq} ${p.name} (${p.strategy})`,
                    })),
                  });
                }
                return (
                  <Form.Item name="rating_method" label="评分方式">
                    <Select placeholder="请选择提示词模板" options={options} />
                  </Form.Item>
                );
              })(          )}
            </>
          )}

          <Form.Item name="objectives" label="关联评估目标">
            <Select placeholder="选择评估目标（一个规则只关联一个目标）"
              options={(objectivesData || []).map((o: any) => ({ value: o.name, label: o.name }))} />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="threshold" label="阈值" initialValue={0.8}><Input type="number" step={0.1} /></Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
          </Space>
          {currentConfig && (
            <div style={{ marginBottom: 8, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6, fontSize: 13, whiteSpace: 'pre-wrap', color: '#555' }}>
              {currentConfig.description}
            </div>
          )}
          <Form.Item name="config" label="配置(JSON)">
            <Input.TextArea rows={4} placeholder={selectedType ? '选择规则类型后将自动生成模板' : '请先选择规则类型'} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="导入评分规则" open={importOpen} onCancel={() => setImportOpen(false)}
        footer={null} width={640}>
        <Upload.Dragger
          accept=".json"
          multiple={false}
          showUploadList={false}
          beforeUpload={(file) => {
            const reader = new FileReader();
            reader.onload = async (e) => {
              try {
                const content = JSON.parse(e.target?.result as string);
                if (!content.rules || !Array.isArray(content.rules)) {
                  message.error('无效的规则文件：缺少 rules 数组');
                  return;
                }
                setImporting(true);
                const result = await rules.importRules(content);
                setImportResult(result);
                queryClient.invalidateQueries({ queryKey: ['rules'] });
                message.success(result.message);
              } catch (err: any) {
                message.error(`导入失败: ${err.message}`);
                setImportResult({ error: err.message });
              } finally {
                setImporting(false);
              }
            };
            reader.readAsText(file);
            return false;
          }}
        >
          <Typography.Text style={{ fontSize: 16 }}><UploadOutlined /></Typography.Text>
          <Typography.Text style={{ display: 'block', marginTop: 8 }}>
            {importing ? '正在导入...' : '点击或拖拽 JSON 规则文件到此区域'}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            支持 评测规则_完整版.json 格式
          </Typography.Text>
        </Upload.Dragger>

        {importResult && !importResult.error && (
          <div style={{ marginTop: 16 }}>
            <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>导入结果:</Typography.Text>
            {importResult.results?.objectives?.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>评估维度:</Typography.Text>
                {importResult.results.objectives.map((o: any, i: number) => (
                  <div key={i} style={{ fontSize: 13, padding: '2px 0' }}>
                    {o.status === 'created' ? '✅' : '❌'} {o.name}
                    {o.error && <Typography.Text type="danger" style={{ fontSize: 12 }}> — {o.error}</Typography.Text>}
                  </div>
                ))}
              </div>
            )}
            {importResult.results?.rules?.length > 0 && (
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>评分规则:</Typography.Text>
                {importResult.results.rules.map((r: any, i: number) => (
                  <div key={i} style={{ fontSize: 13, padding: '2px 0' }}>
                    {r.status === 'created' ? '✅' : '❌'} {r.name}
                    {r.error && <Typography.Text type="danger" style={{ fontSize: 12 }}> — {r.error}</Typography.Text>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {importResult?.error && (
          <div style={{ marginTop: 16 }}>
            <Typography.Text type="danger">导入出错: {importResult.error}</Typography.Text>
          </div>
        )}
      </Modal>

      <Modal title="规则预览" open={previewOpen} onCancel={() => setPreviewOpen(false)} footer={null}>
        {previewResult?.loading ? <Typography.Text>计算中...</Typography.Text> : (
          previewResult ? (
            <div>
              <p><strong>分数:</strong> {previewResult.score}</p>
              <p><strong>通过:</strong> {previewResult.passed ? '✅' : '❌'}</p>
              <p><strong>详情:</strong> {JSON.stringify(previewResult.details)}</p>
              {previewResult.ai_reasoning && <p><strong>AI 分析:</strong> {previewResult.ai_reasoning}</p>}
            </div>
          ) : <Typography.Text type="danger">预览失败</Typography.Text>
        )}
      </Modal>
    </div>
  );
};

export default Rules;
