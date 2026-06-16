import React, { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Upload, Tag, Space, message, Popconfirm } from 'antd';
import { PlusOutlined, UploadOutlined, DeleteOutlined, EditOutlined, EyeOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { datasets, testCases } from '../api/client';

const Datasets: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<any>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editData, setEditData] = useState<any>(null);
  const [datasetEditOpen, setDatasetEditOpen] = useState(false);
  const [datasetEditData, setDatasetEditData] = useState<any>(null);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [datasetEditForm] = Form.useForm();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({ queryKey: ['datasets'], queryFn: () => datasets.list() });

  const createMut = useMutation({
    mutationFn: (d: any) => datasets.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['datasets'] }); message.success('创建成功'); setModalOpen(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => datasets.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['datasets'] }); message.success('已删除'); },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => testCases.update(id, data),
    onSuccess: () => {
      message.success('已更新');
      setEditOpen(false);
      // Refresh detail data if the modal is open
      if (detailData?.dataset?.id) {
        datasets.get(detailData.dataset.id).then(d => setDetailData(d));
      }
    },
    onError: (e: any) => message.error(`更新失败: ${e.message}`),
  });

  const datasetUpdateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => datasets.update(id, data),
    onSuccess: () => {
      message.success('数据集已更新');
      setDatasetEditOpen(false);
      queryClient.invalidateQueries({ queryKey: ['datasets'] });
    },
    onError: (e: any) => message.error(`更新失败: ${e.message}`),
  });

  const handleImport = async (file: File) => {
    try {
      const result = await datasets.import_(file);
      message.success(`导入成功: ${result.cases_imported} 条用例`);
      queryClient.invalidateQueries({ queryKey: ['datasets'] });
    } catch (e: any) {
      message.error(`导入失败: ${e.message}`);
    }
  };

  const viewDetail = async (id: string) => {
    const d = await datasets.get(id);
    setDetailData(d);
    setDetailOpen(true);
  };

  const handleDatasetEdit = (record: any) => {
    setDatasetEditData(record);
    datasetEditForm.setFieldsValue({
      name: record.name,
      description: record.description,
      dataset_type: record.dataset_type,
    });
    setDatasetEditOpen(true);
  };

  const handleDatasetEditSubmit = () => {
    const values = datasetEditForm.getFieldsValue();
    datasetUpdateMut.mutate({ id: datasetEditData.id, data: values });
  };

  const handleEdit = (record: any) => {
    setEditData(record);
    editForm.setFieldsValue({
      case_id: record.case_id,
      input: record.input,
      expected_output: record.expected_output,
      objectives: record.objectives || [],
      tags: record.tags || [],
    });
    setEditOpen(true);
  };

  const handleEditSubmit = () => {
    const values = editForm.getFieldsValue();
    updateMut.mutate({ id: editData.id, data: values });
  };

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'dataset_type', render: (t: string) => t ? <Tag>{t}</Tag> : '-' },
    { title: '版本', dataIndex: 'version', width: 80 },
    { title: '创建时间', dataIndex: 'created_at', render: (t: string) => new Date(t).toLocaleString('zh-CN'), width: 180 },
    {
      title: '操作', width: 220,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => viewDetail(r.id)}>查看</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleDatasetEdit(r)} />
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
        <h1>评测数据集</h1>
        <div className="page-header-actions">
          <Upload accept=".json,.csv,.yaml,.yml,.xlsx" showUploadList={false} customRequest={({ file }) => handleImport(file as File)}>
            <Button icon={<UploadOutlined />}>导入文件</Button>
          </Upload>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>新建数据集</Button>
        </div>
      </div>

      <Table dataSource={data || []} rowKey="id" loading={isLoading} columns={columns} pagination={false} />

      <Modal title="新建数据集" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={(v) => createMut.mutate(v)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea /></Form.Item>
          <Form.Item name="dataset_type" label="类型">
            <Select options={[{ value: 'qa', label: '问答' }, { value: 'instruction', label: '指令执行' }, { value: 'dialogue', label: '多轮对话' }, { value: 'robustness', label: '鲁棒性' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`数据集: ${detailData?.dataset?.name || ''}`} open={detailOpen} onCancel={() => setDetailOpen(false)} width={800} footer={null}>
        {detailData && (
          <Table dataSource={detailData.test_cases || []} rowKey="id" pagination={{ pageSize: 10 }}
            columns={[
              { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
              { title: 'Case ID', dataIndex: 'case_id', width: 120 },
              { title: '输入', dataIndex: 'input', ellipsis: true },
              { title: '期望输出', dataIndex: 'expected_output', ellipsis: true },
              { title: '评测目标', dataIndex: 'objectives', render: (c: string[]) => c?.map(t => <Tag key={t}>{t}</Tag>) },
              {
                title: '操作', width: 80,
                render: (_: any, r: any) => <Button size="small" onClick={() => handleEdit(r)}>编辑</Button>,
              },
            ]}
          />
        )}
      </Modal>

      <Modal title={`编辑数据集: ${datasetEditData?.name || ''}`} open={datasetEditOpen} onCancel={() => setDatasetEditOpen(false)} onOk={() => datasetEditForm.submit()}>
        <Form form={datasetEditForm} layout="vertical" onFinish={(v) => datasetUpdateMut.mutate({ id: datasetEditData.id, data: v })}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea /></Form.Item>
          <Form.Item name="dataset_type" label="类型">
            <Select options={[{ value: 'qa', label: '问答' }, { value: 'instruction', label: '指令执行' }, { value: 'dialogue', label: '多轮对话' }, { value: 'robustness', label: '鲁棒性' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`编辑用例: ${editData?.case_id || ''}`} open={editOpen} onCancel={() => setEditOpen(false)} onOk={handleEditSubmit} width={720}>
        <Form form={editForm} layout="vertical">
          <Form.Item name="case_id" label="Case ID" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="input" label="输入" rules={[{ required: true }]}>
            <Input.TextArea rows={4} placeholder="测试输入内容" />
          </Form.Item>
          <Form.Item name="expected_output" label="期望输出">
            <Input.TextArea rows={4} placeholder="期望的标准输出" />
          </Form.Item>
          <Form.Item name="objectives" label="评测目标">
            <Select mode="tags" placeholder="输入评测目标名称后回车添加"
              options={[
                { value: '准确性', label: '准确性' },
                { value: '完整性', label: '完整性' },
                { value: '清晰度', label: '清晰度' },
                { value: '相关性', label: '相关性' },
                { value: '安全性', label: '安全性' },
              ]} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后回车添加" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Datasets;
