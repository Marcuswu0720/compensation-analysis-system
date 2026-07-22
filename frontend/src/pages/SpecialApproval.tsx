import { useState } from 'react';
import { Alert, Button, Card, Input, Modal, Space, Table, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { leaveApi, overtimeApi } from '../api/leaveOvertime';
import { useLocalizedName } from '../utils/status';

function useApprovalActions(queryKey: string[], approveFn: (id: string, c?: string) => Promise<unknown>, rejectFn: (id: string, c?: string) => Promise<unknown>) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [modal, setModal] = useState<{ id: string; action: 'approve' | 'reject' } | null>(null);
  const [comment, setComment] = useState('');

  const mutation = useMutation({
    mutationFn: async () => {
      if (!modal) return;
      if (modal.action === 'approve') return approveFn(modal.id, comment);
      return rejectFn(modal.id, comment);
    },
    onSuccess: () => {
      message.success(t('common.opSuccess'));
      setModal(null);
      setComment('');
      queryClient.invalidateQueries({ queryKey });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('common.opFailed')),
  });

  return { modal, setModal, comment, setComment, mutation };
}

function LeaveSpecialTab() {
  const { t } = useTranslation();
  const localizedName = useLocalizedName();
  const { data = [] } = useQuery({ queryKey: ['leave-special-pending'], queryFn: leaveApi.specialPending });
  const { modal, setModal, comment, setComment, mutation } = useApprovalActions(
    ['leave-special-pending'],
    leaveApi.specialApprove,
    leaveApi.specialReject,
  );

  return (
    <>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        locale={{ emptyText: t('specialApproval.noLeavePending') }}
        columns={[
          { title: t('common.employee'), render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: t('common.type'), render: (_, r: any) => localizedName(r.type) },
          { title: t('common.startTime'), dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: t('common.endTime'), dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: t('common.reason'), dataIndex: 'reason' },
          {
            title: t('common.actions'),
            render: (_, r: any) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                  {t('specialApproval.approve')}
                </Button>
                <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                  {t('specialApproval.reject')}
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? t('specialApproval.approveTitle') : t('specialApproval.rejectTitle')}
        open={!!modal}
        onCancel={() => setModal(null)}
        onOk={() => mutation.mutate()}
        confirmLoading={mutation.isPending}
      >
        <Input.TextArea rows={3} placeholder={t('common.approvalCommentOptional')} value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>
    </>
  );
}

function OvertimeSpecialTab() {
  const { t } = useTranslation();
  const { data = [] } = useQuery({ queryKey: ['overtime-special-pending'], queryFn: overtimeApi.specialPending });
  const { modal, setModal, comment, setComment, mutation } = useApprovalActions(
    ['overtime-special-pending'],
    overtimeApi.specialApprove,
    overtimeApi.specialReject,
  );

  return (
    <>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        locale={{ emptyText: t('specialApproval.noOvertimePending') }}
        columns={[
          { title: t('common.employee'), render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: t('common.date'), dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: t('myApplications.hours'), dataIndex: 'hours' },
          { title: t('common.reason'), dataIndex: 'reason' },
          {
            title: t('common.actions'),
            render: (_, r: any) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                  {t('specialApproval.approve')}
                </Button>
                <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                  {t('specialApproval.reject')}
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? t('specialApproval.approveTitle') : t('specialApproval.rejectTitle')}
        open={!!modal}
        onCancel={() => setModal(null)}
        onOk={() => mutation.mutate()}
        confirmLoading={mutation.isPending}
      >
        <Input.TextArea rows={3} placeholder={t('common.approvalCommentOptional')} value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>
    </>
  );
}

export default function SpecialApproval() {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={3}>{t('specialApproval.title')}</Typography.Title>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t('specialApproval.banner')}
      />
      <Card>
        <Tabs
          items={[
            { key: 'leave', label: t('specialApproval.leaveTab'), children: <LeaveSpecialTab /> },
            { key: 'overtime', label: t('specialApproval.overtimeTab'), children: <OvertimeSpecialTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
