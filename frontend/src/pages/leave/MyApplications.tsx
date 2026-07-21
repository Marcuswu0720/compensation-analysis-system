import { Button, Card, Popconfirm, Table, Tabs, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { leaveApi, overtimeApi } from '../../api/leaveOvertime';
import { APPROVAL_COLOR, useApprovalLabel } from '../../utils/status';

function LeaveTab() {
  const { t } = useTranslation();
  const approvalLabel = useApprovalLabel();
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['my-leave'], queryFn: leaveApi.mine });
  const cancelMutation = useMutation({
    mutationFn: leaveApi.cancel,
    onSuccess: () => {
      message.success(t('myApplications.revoked'));
      queryClient.invalidateQueries({ queryKey: ['my-leave'] });
    },
  });

  return (
    <Table
      rowKey="id"
      scroll={{ x: "max-content" }}
      dataSource={data}
      pagination={{ pageSize: 10 }}
      columns={[
        { title: t('common.type'), dataIndex: ['type', 'name'] },
        { title: t('common.startTime'), dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
        { title: t('common.endTime'), dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
        { title: t('common.reason'), dataIndex: 'reason' },
        { title: t('common.status'), dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as keyof typeof APPROVAL_COLOR]}>{approvalLabel[v as keyof typeof approvalLabel]}</Tag> },
        { title: t('myApplications.approveComment'), dataIndex: 'approveComment' },
        {
          title: t('common.actions'),
          render: (_, record) =>
            record.status === 'PENDING' ? (
              <Popconfirm title={t('common.confirmRevoke')} onConfirm={() => cancelMutation.mutate(record.id)}>
                <Button size="small" danger>
                  {t('common.revoke')}
                </Button>
              </Popconfirm>
            ) : null,
        },
      ]}
    />
  );
}

function OvertimeTab() {
  const { t } = useTranslation();
  const approvalLabel = useApprovalLabel();
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['my-overtime'], queryFn: overtimeApi.mine });
  const cancelMutation = useMutation({
    mutationFn: overtimeApi.cancel,
    onSuccess: () => {
      message.success(t('myApplications.revoked'));
      queryClient.invalidateQueries({ queryKey: ['my-overtime'] });
    },
  });

  return (
    <Table
      rowKey="id"
      scroll={{ x: "max-content" }}
      dataSource={data}
      pagination={{ pageSize: 10 }}
      columns={[
        { title: t('common.date'), dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
        { title: t('myApplications.hours'), dataIndex: 'hours' },
        { title: t('common.reason'), dataIndex: 'reason' },
        { title: t('common.status'), dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as keyof typeof APPROVAL_COLOR]}>{approvalLabel[v as keyof typeof approvalLabel]}</Tag> },
        { title: t('myApplications.approveComment'), dataIndex: 'approveComment' },
        {
          title: t('common.actions'),
          render: (_, record) =>
            record.status === 'PENDING' ? (
              <Popconfirm title={t('common.confirmRevoke')} onConfirm={() => cancelMutation.mutate(record.id)}>
                <Button size="small" danger>
                  {t('common.revoke')}
                </Button>
              </Popconfirm>
            ) : null,
        },
      ]}
    />
  );
}

export default function MyApplications() {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={3}>{t('myApplications.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'leave', label: t('myApplications.leaveTab'), children: <LeaveTab /> },
            { key: 'overtime', label: t('myApplications.overtimeTab'), children: <OvertimeTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
