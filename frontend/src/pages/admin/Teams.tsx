import { useState } from 'react';
import { Button, Card, Form, Input, Modal, Select, Table, Tabs, Tree, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { departmentsApi, teamsApi, officesApi } from '../../api/org';
import { useModeLabel } from '../../utils/status';
import type { AttendanceMode, Department } from '../../api/types';

function toTreeData(depts: Department[]): any[] {
  return depts.map((d) => ({ key: d.id, title: d.name, children: d.children ? toTreeData(d.children) : [] }));
}

function DepartmentsTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: tree = [] } = useQuery({ queryKey: ['dept-tree'], queryFn: departmentsApi.tree });
  const { data: departments = [] } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.list });
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: departmentsApi.create,
    onSuccess: () => {
      message.success(t('common.createSuccess'));
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['dept-tree'] });
      queryClient.invalidateQueries({ queryKey: ['departments'] });
    },
  });

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        {t('adminTeams.addDepartment')}
      </Button>
      <Tree treeData={toTreeData(tree)} defaultExpandAll />
      <Modal title={t('adminTeams.addDepartmentTitle')} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label={t('adminTeams.departmentName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="parentId" label={t('adminTeams.parentDepartment')}>
            <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function TeamsTab() {
  const { t } = useTranslation();
  const modeLabel = useModeLabel();
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const { data: departments = [] } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.list });
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: teamsApi.create,
    onSuccess: () => {
      message.success(t('common.createSuccess'));
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });

  const modeMutation = useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: AttendanceMode }) => teamsApi.setModeConfig(id, mode),
    onSuccess: () => {
      message.success(t('adminTeams.modeUpdated'));
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        {t('adminTeams.addTeam')}
      </Button>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={teams}
        columns={[
          { title: t('adminTeams.teamName'), dataIndex: 'name' },
          { title: t('adminTeams.belongingDepartment'), dataIndex: ['department', 'name'] },
          {
            title: t('adminTeams.modeColumn'),
            render: (_, r: any) => (
              <Select
                style={{ width: 160 }}
                value={r.modeConfig?.mode}
                placeholder={t('adminTeams.modeNotSet')}
                onChange={(mode) => modeMutation.mutate({ id: r.id, mode })}
                options={Object.entries(modeLabel).map(([k, v]) => ({ value: k, label: v }))}
              />
            ),
          },
        ]}
      />
      <Modal title={t('adminTeams.addTeamTitle')} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label={t('adminTeams.teamName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="departmentId" label={t('adminTeams.belongingDepartment')} rules={[{ required: true }]}>
            <Select options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function OfficesTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: offices = [] } = useQuery({ queryKey: ['offices'], queryFn: officesApi.list });
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const createMutation = useMutation({
    mutationFn: officesApi.create,
    onSuccess: () => {
      message.success(t('common.createSuccess'));
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['offices'] });
    },
  });

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        {t('adminTeams.addOffice')}
      </Button>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={offices}
        columns={[
          { title: t('adminTeams.officeName'), dataIndex: 'name' },
          { title: t('adminTeams.address'), dataIndex: 'address' },
          { title: t('adminTeams.lat'), dataIndex: 'gpsLat' },
          { title: t('adminTeams.lng'), dataIndex: 'gpsLng' },
        ]}
      />
      <Modal title={t('adminTeams.addOfficeTitle')} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label={t('adminTeams.officeName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="address" label={t('adminTeams.address')}>
            <Input />
          </Form.Item>
          <Form.Item name="gpsLat" label={t('adminTeams.lat')}>
            <Input type="number" />
          </Form.Item>
          <Form.Item name="gpsLng" label={t('adminTeams.lng')}>
            <Input type="number" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default function Teams() {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={3}>{t('adminTeams.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'departments', label: t('adminTeams.departmentsTab'), children: <DepartmentsTab /> },
            { key: 'teams', label: t('adminTeams.teamsTab'), children: <TeamsTab /> },
            { key: 'offices', label: t('adminTeams.officesTab'), children: <OfficesTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
