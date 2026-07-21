import { useState } from 'react';
import { Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tag, Typography, Upload, message } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { usersApi, departmentsApi, teamsApi } from '../../api/org';
import { useRoleLabel } from '../../utils/status';
import type { Role } from '../../api/types';

export default function Employees() {
  const { t } = useTranslation();
  const roleLabel = useRoleLabel();
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
      message.success(t('common.createSuccess'));
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('common.createFailed')),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => (active ? usersApi.enable(id) : usersApi.disable(id)),
    onSuccess: () => {
      message.success(t('common.opSuccess'));
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const importMutation = useMutation({
    mutationFn: usersApi.importExcel,
    onSuccess: (res: any) => {
      message.success(t('adminEmployees.importDone', { success: res.success, total: res.total }));
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('adminEmployees.importFailed')),
  });

  return (
    <div>
      <Typography.Title level={3}>{t('adminEmployees.title')}</Typography.Title>
      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input.Search placeholder={t('adminEmployees.searchPlaceholder')} onSearch={setKeyword} style={{ width: 240 }} allowClear />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            {t('adminEmployees.addEmployee')}
          </Button>
          <Upload
            showUploadList={false}
            accept=".xlsx,.xls,.csv"
            customRequest={({ file }) => importMutation.mutate(file as File)}
          >
            <Button icon={<UploadOutlined />} loading={importMutation.isPending}>
              {t('adminEmployees.importExcel')}
            </Button>
          </Upload>
        </Space>
        <Table
          rowKey="id"
          scroll={{ x: "max-content" }}
          loading={isLoading}
          dataSource={users}
          columns={[
            { title: t('adminEmployees.employeeNo'), dataIndex: 'employeeNo' },
            { title: t('adminEmployees.name'), dataIndex: 'name' },
            { title: t('adminEmployees.email'), dataIndex: 'email' },
            { title: t('adminEmployees.role'), dataIndex: 'role', render: (v: Role) => roleLabel[v] },
            { title: t('adminEmployees.department'), render: (_, r: any) => r.department?.name },
            { title: t('adminEmployees.team'), render: (_, r: any) => r.team?.name },
            { title: t('adminEmployees.status'), dataIndex: 'isActive', render: (v) => (v ? <Tag color="green">{t('common.enabled')}</Tag> : <Tag color="red">{t('common.disabled')}</Tag>) },
            {
              title: t('common.actions'),
              render: (_, r: any) => (
                <Switch checked={r.isActive} onChange={(checked) => toggleActiveMutation.mutate({ id: r.id, active: checked })} checkedChildren={t('common.enable')} unCheckedChildren={t('common.disable')} />
              ),
            },
          ]}
        />
      </Card>

      <Modal title={t('adminEmployees.addEmployeeTitle')} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form layout="vertical" form={form} onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="employeeNo" label={t('adminEmployees.employeeNo')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name" label={t('adminEmployees.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label={t('adminEmployees.email')} rules={[{ required: true, type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t('adminEmployees.initialPassword')} rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label={t('adminEmployees.role')} initialValue="EMPLOYEE">
            <Select options={Object.entries(roleLabel).map(([k, v]) => ({ value: k, label: v }))} />
          </Form.Item>
          <Form.Item name="departmentId" label={t('adminEmployees.department')}>
            <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item name="teamId" label={t('adminEmployees.team')}>
            <Select allowClear options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
          </Form.Item>
          <Form.Item name="position" label={t('adminEmployees.position')}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
