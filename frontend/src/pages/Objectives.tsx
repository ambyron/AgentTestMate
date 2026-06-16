import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Space, message, Tag, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { objectives } from '../api/client';

const Objectives: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: ['objectives'], queryFn: () => objectives.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => editing ? objectives.update(editing.id, d) : objectives.create(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['objectives'] });
      message.success(editing ? '更新成功' : '创建成功');
      setModalOpen(false);
    },
    onError: (err: any) => {
      message.error(`保存失败: ${err?.response?.data?.detail || err.message}`);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => objectives.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['objectives'] });
      message.success('已删除');
    },
  });

  const openEdit = (record?: any) => {
    setEditing(record);
    form.setFieldsValue(record || { name: '', description: '', default_weight: 1.0 });
    setModalOpen(true);
  };

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '名称', dataIndex: 'name', width: 180 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '默认权重', dataIndex: 'default_weight', width: 100,
      render: (v: number) => <Tag>{v}</Tag> },
    {
      title: '操作', width: 120,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="确定删除该目标?" onConfirm={() => deleteMut.mutate(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>目标配置</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>新建目标</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title={editing ? '编辑目标' : '新建目标'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={520}>
        <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入目标名称' }]}>
            <Input placeholder="如：准确性、完整性" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="目标的详细说明" />
          </Form.Item>
          <Form.Item name="default_weight" label="默认权重" rules={[{ required: true }]}>
            <InputNumber min={0} max={10} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Objectives;
