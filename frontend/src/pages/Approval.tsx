import { useState } from 'react';
import { Button, Card, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { leaveApi, overtimeApi } from '../api/leaveOvertime';
import { APPROVAL_COLOR, useApprovalLabel, useLocalizedName } from '../utils/status';
import type { ApprovalStatus } from '../api/types';

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

function LeaveApprovalTab() {
  const { t } = useTranslation();
  const approvalLabel = useApprovalLabel();
  const localizedName = useLocalizedName();
  const [status, setStatus] = useState<ApprovalStatus>('PENDING');
  const { data = [] } = useQuery({ queryKey: ['leave-approvals', status], queryFn: () => leaveApi.list({ status }) });
  const { modal, setModal, comment, setComment, mutation } = useApprovalActions(['leave-approvals'], leaveApi.approve, leaveApi.reject);

  return (
    <>
      <Select value={status} onChange={setStatus} style={{ width: 160, marginBottom: 12 }} options={Object.entries(approvalLabel).map(([k, v]) => ({ value: k, label: v }))} />
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: t('common.employee'), render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: t('common.type'), render: (_, r: any) => localizedName(r.type) },
          { title: t('common.startTime'), dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: t('common.endTime'), dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: t('common.reason'), dataIndex: 'reason' },
          { title: t('common.status'), dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as ApprovalStatus]}>{approvalLabel[v as ApprovalStatus]}</Tag> },
          {
            title: t('common.actions'),
            render: (_, r: any) =>
              r.status === 'PENDING' ? (
                <Space>
                  <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                    {t('common.approve')}
                  </Button>
                  <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                    {t('common.reject')}
                  </Button>
                </Space>
              ) : null,
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? t('approval.approveTitle') : t('approval.rejectTitle')}
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

function OvertimeApprovalTab() {
  const { t } = useTranslation();
  const approvalLabel = useApprovalLabel();
  const [status, setStatus] = useState<ApprovalStatus>('PENDING');
  const { data = [] } = useQuery({ queryKey: ['overtime-approvals', status], queryFn: () => overtimeApi.list({ status }) });
  const { modal, setModal, comment, setComment, mutation } = useApprovalActions(['overtime-approvals'], overtimeApi.approve, overtimeApi.reject);

  return (
    <>
      <Select value={status} onChange={setStatus} style={{ width: 160, marginBottom: 12 }} options={Object.entries(approvalLabel).map(([k, v]) => ({ value: k, label: v }))} />
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: t('common.employee'), render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: t('common.date'), dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: t('myApplications.hours'), dataIndex: 'hours' },
          { title: t('common.reason'), dataIndex: 'reason' },
          { title: t('common.status'), dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as ApprovalStatus]}>{approvalLabel[v as ApprovalStatus]}</Tag> },
          {
            title: t('common.actions'),
            render: (_, r: any) =>
              r.status === 'PENDING' ? (
                <Space>
                  <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                    {t('common.approve')}
                  </Button>
                  <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                    {t('common.reject')}
                  </Button>
                </Space>
              ) : null,
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? t('approval.approveTitle') : t('approval.rejectTitle')}
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

export default function Approval() {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={3}>{t('approval.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'leave', label: t('approval.leaveTab'), children: <LeaveApprovalTab /> },
            { key: 'overtime', label: t('approval.overtimeTab'), children: <OvertimeApprovalTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
