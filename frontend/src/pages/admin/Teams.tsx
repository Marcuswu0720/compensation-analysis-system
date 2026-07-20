import { useState } from 'react';
import { Button, Card, Form, Input, Modal, Select, Table, Tabs, Tree, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { departmentsApi, teamsApi, officesApi } from '../../api/org';
import { MODE_LABEL } from '../../utils/status';
import type { AttendanceMode, Department } from '../../api/types';

function toTreeData(depts: Department[]): any[] {
  return depts.map((d) => ({ key: d.id, title: d.name, children: d.children ? toTreeData(d.children) : [] }));
}

function DepartmentsTab() {
  const queryClient = useQueryClient();
  const { data: tree = [] } = useQuery({ queryKey: ['dept-tree'], queryFn: departmentsApi.tree });
  const { data: departments = [] } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.list });
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: departmentsApi.create,
    onSuccess: () => {
      message.success('创建成功');
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['dept-tree'] });
      queryClient.invalidateQueries({ queryKey: ['departments'] });
    },
  });

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        新增部门
      </Button>
      <Tree treeData={toTreeData(tree)} defaultExpandAll />
      <Modal title="新增部门" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label="部门名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="parentId" label="上级部门">
            <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function TeamsTab() {
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const { data: departments = [] } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.list });
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: teamsApi.create,
    onSuccess: () => {
      message.success('创建成功');
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });

  const modeMutation = useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: AttendanceMode }) => teamsApi.setModeConfig(id, mode),
    onSuccess: () => {
      message.success('打卡模式已更新');
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        新增团队
      </Button>
      <Table
        rowKey="id"
        dataSource={teams}
        columns={[
          { title: '团队名称', dataIndex: 'name' },
          { title: '所属部门', dataIndex: ['department', 'name'] },
          {
            title: '打卡模式（第3.2节，可随时调整）',
            render: (_, r: any) => (
              <Select
                style={{ width: 160 }}
                value={r.modeConfig?.mode}
                placeholder="未设置"
                onChange={(mode) => modeMutation.mutate({ id: r.id, mode })}
                options={Object.entries(MODE_LABEL).map(([k, v]) => ({ value: k, label: v }))}
              />
            ),
          },
        ]}
      />
      <Modal title="新增团队" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label="团队名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="departmentId" label="所属部门" rules={[{ required: true }]}>
            <Select options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function OfficesTab() {
  const queryClient = useQueryClient();
  const { data: offices = [] } = useQuery({ queryKey: ['offices'], queryFn: officesApi.list });
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: officesApi.create,
    onSuccess: () => {
      message.success('创建成功');
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['offices'] });
    },
  });

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        新增办公室
      </Button>
      <Table
        rowKey="id"
        dataSource={offices}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '地址', dataIndex: 'address' },
          { title: '纬度', dataIndex: 'gpsLat' },
          { title: '经度', dataIndex: 'gpsLng' },
        ]}
      />
      <Modal title="新增办公室" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <Input />
          </Form.Item>
          <Form.Item name="gpsLat" label="纬度">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="gpsLng" label="经度">
            <Input type="number" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default function Teams() {
  return (
    <div>
      <Typography.Title level={3}>部门/团队管理</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'departments', label: '部门树', children: <DepartmentsTab /> },
            { key: 'teams', label: '团队 + 打卡模式映射', children: <TeamsTab /> },
            { key: 'offices', label: '办公室', children: <OfficesTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
