import React, { useState, useEffect, useCallback } from 'react';
import { Table, Button, Modal, Form, Input, Select, Switch, Space, message, Tag, Popconfirm } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { users as usersApi } from '../api/client';
import type { User } from '../types';

const Users: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [search, setSearch] = useState('');
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const fetchUsers = useCallback(async (searchTerm: string) => {
    setLoading(true);
    try {
      const data = await usersApi.list({ search: searchTerm });
      setUsers(data || []);
    } catch (err: any) {
      console.error('Failed to load users:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers(search);
  }, [search, fetchUsers]);

  const afterMutation = () => {
    fetchUsers(search);
  };

  const createMut = async (values: any) => {
    try {
      if (editing) {
        await usersApi.update(editing.id, values);
      } else {
        await usersApi.create(values);
      }
      afterMutation();
      message.success('保存成功');
      setModalOpen(false);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  const deleteUser = async (id: string) => {
    try {
      await usersApi.delete(id);
      afterMutation();
      message.success('已删除');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败');
    }
  };

  const toggleActive = async (id: string) => {
    try {
      await usersApi.toggleActive(id);
      afterMutation();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  const openEdit = (record?: User) => {
    setEditing(record || null);
    if (record) {
      form.setFieldsValue(record);
    } else {
      form.resetFields();
    }
    setModalOpen(true);
  };

  const columns = [
    { title: '#', key: 'index', width: 60, render: (_: any, __: any, i: number) => i + 1 },
    { title: '用户名', dataIndex: 'username' },
    { title: '邮箱', dataIndex: 'email', render: (v: string) => v || '-' },
    {
      title: '角色', dataIndex: 'role', width: 100,
      render: (v: string) => v === 'admin' ? <Tag color="blue">管理员</Tag> : <Tag>用户</Tag>,
    },
    {
      title: '状态', dataIndex: 'is_active', width: 80,
      render: (v: boolean, record: User) => (
        <Switch
          size="small"
          checked={v}
          disabled={record.username === 'admin'}
          onChange={() => toggleActive(record.id)}
        />
      ),
    },
    { title: '显示名称', dataIndex: 'display_name', render: (v: string) => v || '-' },
    { title: '最后登录', dataIndex: 'last_login', width: 180, render: (v: string) => v || '-' },
    {
      title: '操作', width: 120,
      render: (_: any, r: User) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm
            title="确定删除?"
            description={r.username === 'admin' ? '无法删除默认管理员' : undefined}
            onConfirm={() => deleteUser(r.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.username === 'admin'} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>用户管理</h1>
        <div className="page-header-actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>新建用户</Button>
        </div>
      </div>

      <div className="page-toolbar">
        <Input.Search
          placeholder="搜索用户名..."
          style={{ width: 240 }}
          allowClear
          onSearch={(v) => setSearch(v)}
        />
      </div>

      <div className="section-card">
        <Table
          dataSource={users}
          rowKey="id"
          loading={loading}
          columns={columns}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
        />
      </div>

      <Modal
        title={editing ? '编辑用户' : '新建用户'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={(v) => createMut(v)}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input disabled={!!editing} placeholder="登录用用户名" />
          </Form.Item>
          {!editing && (
            <Form.Item name="password" label="密码" rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少 8 位' },
            ]}>
              <Input.Password placeholder="至少 8 位" />
            </Form.Item>
          )}
          <Form.Item name="email" label="邮箱">
            <Input placeholder="电子邮箱(可选)" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input placeholder="显示名称(可选)" />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="user">
            <Select options={[
              { value: 'user', label: '用户' },
              { value: 'admin', label: '管理员' },
            ]} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Users;
