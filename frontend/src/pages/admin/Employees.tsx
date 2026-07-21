import { useState } from 'react';
import { Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tag, Typography, Upload, message } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usersApi, departmentsApi, teamsApi } from '../../api/org';
import { ROLE_LABEL } from '../../utils/status';
import type { Role } from '../../api/types';

export default function Employees() {
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: users = [], isLoading } = useQuery({ queryKey: ['users', keyword], queryFn: () => usersApi.list({ keyword: keyword || undefined }) });
  const { data: departments = [] } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.list });
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });

  const createMutation = useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => {
      message.success('创建成功');
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '创建失败'),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => (active ? usersApi.enable(id) : usersApi.disable(id)),
    onSuccess: () => {
      message.success('操作成功');
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const importMutation = useMutation({
    mutationFn: usersApi.importExcel,
    onSuccess: (res: any) => {
      message.success(`导入完成：成功 ${res.success}/${res.total}`);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '导入失败'),
  });

  return (
    <div>
      <Typography.Title level={3}>员工管理</Typography.Title>
      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input.Search placeholder="搜索姓名/工号/邮箱" onSearch={setKeyword} style={{ width: 240 }} allowClear />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新增员工
          </Button>
          <Upload
            showUploadList={false}
            accept=".xlsx,.xls,.csv"
            customRequest={({ file }) => importMutation.mutate(file as File)}
          >
            <Button icon={<UploadOutlined />} loading={importMutation.isPending}>
              批量导入（Excel）
            </Button>
          </Upload>
        </Space>
        <Table
          rowKey="id"
          scroll={{ x: "max-content" }}
          loading={isLoading}
          dataSource={users}
          columns={[
            { title: '工号', dataIndex: 'employeeNo' },
            { title: '姓名', dataIndex: 'name' },
            { title: '邮箱', dataIndex: 'email' },
            { title: '角色', dataIndex: 'role', render: (v: Role) => ROLE_LABEL[v] },
            { title: '部门', render: (_, r: any) => r.department?.name },
            { title: '团队', render: (_, r: any) => r.team?.name },
            { title: '状态', dataIndex: 'isActive', render: (v) => (v ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>) },
            {
              title: '操作',
              render: (_, r: any) => (
                <Switch checked={r.isActive} onChange={(checked) => toggleActiveMutation.mutate({ id: r.id, active: checked })} checkedChildren="启用" unCheckedChildren="禁用" />
              ),
            },
          ]}
        />
      </Card>

      <Modal title="新增员工" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="employeeNo" label="工号" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="EMPLOYEE">
            <Select options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ value: k, label: v }))} />
          </Form.Item>
          <Form.Item name="departmentId" label="部门">
            <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item name="teamId" label="团队">
            <Select allowClear options={teams.map((t) => ({ value: t.id, label: t.name }))} />
          </Form.Item>
          <Form.Item name="position" label="职位">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
