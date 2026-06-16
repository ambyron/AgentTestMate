import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, InputNumber, Space, message, Tag, Popconfirm } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { scoreConfigs } from '../api/client';

const DATA_TYPES = [
  { value: 'NUMERIC', label: '数值评分 (NUMERIC)' },
  { value: 'BOOLEAN', label: '布尔评分 (BOOLEAN)' },
  { value: 'CATEGORICAL', label: '分类评分 (CATEGORICAL)' },
];

const DATA_TYPE_COLORS: Record<string, string> = {
  NUMERIC: 'blue',
  BOOLEAN: 'green',
  CATEGORICAL: 'purple',
};

const ScoreConfigs: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: ['score-configs'], queryFn: () => scoreConfigs.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => editing ? scoreConfigs.update(editing.id, d) : scoreConfigs.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['score-configs'] }); message.success('保存成功'); setModalOpen(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => scoreConfigs.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['score-configs'] }); message.success('已删除'); },
  });

  const openEdit = (record?: any) => {
    setEditing(record);
    if (record) {
      form.setFieldsValue(record);
    } else {
      form.resetFields();
      form.setFieldsValue({ data_type: 'NUMERIC' });
    }
    setModalOpen(true);
  };

  const dataType = Form.useWatch('data_type', form);

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '名称', dataIndex: 'name' },
    { title: '数据类型', dataIndex: 'data_type', render: (t: string) => <Tag color={DATA_TYPE_COLORS[t]}>{t}</Tag> },
    {
      title: '约束', render: (_: any, r: any) => {
        if (r.data_type === 'NUMERIC') return `${r.min_value ?? 0} ~ ${r.max_value ?? 1}`;
        if (r.data_type === 'BOOLEAN') return '0 / 1';
        if (r.data_type === 'CATEGORICAL') return (r.categories || []).map((c: any) => c.label || c).join(', ');
        return '-';
      },
    },
    {
      title: '操作', width: 120,
      render: (_: any, r: any) => (
        <Space>
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
        <h1>评分配置</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>新建配置</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title={editing ? '编辑评分配置' : '新建评分配置'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={520}>
        <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="data_type" label="数据类型" rules={[{ required: true }]}>
            <Select options={DATA_TYPES} />
          </Form.Item>

          {dataType === 'NUMERIC' && (
            <Space style={{ width: '100%' }}>
              <Form.Item name="min_value" label="最小值"><InputNumber step={0.1} /></Form.Item>
              <Form.Item name="max_value" label="最大值"><InputNumber step={0.1} /></Form.Item>
            </Space>
          )}

          {dataType === 'CATEGORICAL' && (
            <Form.Item name="categories" label="分类选项">
              <Select mode="tags" placeholder="输入分类标签后回车，如: pass,fail,needs_review" />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default ScoreConfigs;
