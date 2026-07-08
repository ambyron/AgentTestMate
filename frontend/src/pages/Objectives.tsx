import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Space, message, Tag, Popconfirm, Descriptions, Spin } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { objectives } from '../api/client';

const Objectives: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [viewData, setViewData] = useState<any>(null);
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

  const [deleting, setDeleting] = useState<string | null>(null);

  const deleteMut = useMutation({
    mutationFn: (id: string) => objectives.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['objectives'] });
      message.success('已删除');
    },
    onError: (err: any) => {
      message.error(`删除失败: ${err?.response?.data?.detail || err.message}`);
    },
  });

  const handleDelete = async (record: any) => {
    setDeleting(record.id);
    try {
      const detail = await objectives.get(record.id);
      if (detail.rules && detail.rules.length > 0) {
        message.error('有使用此评估目标的评估规则，不允许删除');
        return;
      }
      deleteMut.mutate(record.id);
    } catch (err: any) {
      message.error(`删除失败: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  const openEdit = (record?: any) => {
    setEditing(record);
    form.setFieldsValue(record || { name: '', description: '' });
    setModalOpen(true);
  };

  const openView = async (record: any) => {
    setViewData(null);
    setViewOpen(true);
    try {
      const data = await objectives.get(record.id);
      setViewData(data);
    } catch (err: any) {
      message.error(`加载失败: ${err?.response?.data?.detail || err.message}`);
      setViewOpen(false);
    }
  };

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '操作', width: 160,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openView(r)}>查看</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="确定删除该目标?" onConfirm={() => handleDelete(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} loading={deleting === r.id} />
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

      {/* ─── Create / Edit modal ─── */}
      <Modal title={editing ? '编辑目标' : '新建目标'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()} width={520}>
        <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入目标名称' }]}>
            <Input placeholder="如：准确性、完整性" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="目标的详细说明" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ─── View modal ─── */}
      <Modal title="目标详情" open={viewOpen} onCancel={() => setViewOpen(false)}
        footer={<Button onClick={() => setViewOpen(false)}>关闭</Button>} width={600}>
        {!viewData ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : (
          <div>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 20 }}>
              <Descriptions.Item label="名称">{viewData.name}</Descriptions.Item>
              <Descriptions.Item label="描述">{viewData.description || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {viewData.created_at ? new Date(viewData.created_at).toLocaleString('zh-CN') : '-'}
              </Descriptions.Item>
            </Descriptions>

            <h4 style={{ marginBottom: 12 }}>关联的评估规则</h4>
            {viewData.rules && viewData.rules.length > 0 ? (
              <Table dataSource={viewData.rules} rowKey="id" pagination={false}
                columns={[
                  { title: '名称', dataIndex: 'name', ellipsis: true },
                  { title: '类型', dataIndex: 'type', width: 120,
                    render: (v: string) => <Tag>{v}</Tag>,
                  },
                  { title: '权重', dataIndex: 'weight', width: 80,
                    render: (v: number) => <Tag>{v}</Tag>,
                  },
                  { title: '状态', dataIndex: 'enabled', width: 80,
                    render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag color="default">禁用</Tag>,
                  },
                ]}
              />
            ) : (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--gray-400)' }}>
                暂无关联的评估规则
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Objectives;
