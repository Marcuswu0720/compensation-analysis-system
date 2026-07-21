import { useState } from 'react';
import { Button, Card, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { leaveApi, overtimeApi } from '../api/leaveOvertime';
import { APPROVAL_COLOR, APPROVAL_LABEL } from '../utils/status';
import type { ApprovalStatus } from '../api/types';

function useApprovalActions(queryKey: string[], approveFn: (id: string, c?: string) => Promise<unknown>, rejectFn: (id: string, c?: string) => Promise<unknown>) {
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
      message.success('操作成功');
      setModal(null);
      setComment('');
      queryClient.invalidateQueries({ queryKey });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '操作失败'),
  });

  return { modal, setModal, comment, setComment, mutation };
}

function LeaveApprovalTab() {
  const [status, setStatus] = useState<ApprovalStatus>('PENDING');
  const { data = [] } = useQuery({ queryKey: ['leave-approvals', status], queryFn: () => leaveApi.list({ status }) });
  const { modal, setModal, comment, setComment, mutation } = useApprovalActions(['leave-approvals'], leaveApi.approve, leaveApi.reject);

  return (
    <>
      <Select value={status} onChange={setStatus} style={{ width: 160, marginBottom: 12 }} options={Object.entries(APPROVAL_LABEL).map(([k, v]) => ({ value: k, label: v }))} />
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: '员工', render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: '类型', dataIndex: ['type', 'name'] },
          { title: '开始', dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: '结束', dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: '事由', dataIndex: 'reason' },
          { title: '状态', dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as ApprovalStatus]}>{APPROVAL_LABEL[v as ApprovalStatus]}</Tag> },
          {
            title: '操作',
            render: (_, r: any) =>
              r.status === 'PENDING' ? (
                <Space>
                  <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                    通过
                  </Button>
                  <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                    驳回
                  </Button>
                </Space>
              ) : null,
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? '通过申请' : '驳回申请'}
        open={!!modal}
        onCancel={() => setModal(null)}
        onOk={() => mutation.mutate()}
        confirmLoading={mutation.isPending}
      >
        <Input.TextArea rows={3} placeholder="审批意见（可选）" value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>
    </>
  );
}

function OvertimeApprovalTab() {
  const [status, setStatus] = useState<ApprovalStatus>('PENDING');
  const { data = [] } = useQuery({ queryKey: ['overtime-approvals', status], queryFn: () => overtimeApi.list({ status }) });
  const { modal, setModal, comment, setComment, mutation } = useApprovalActions(['overtime-approvals'], overtimeApi.approve, overtimeApi.reject);

  return (
    <>
      <Select value={status} onChange={setStatus} style={{ width: 160, marginBottom: 12 }} options={Object.entries(APPROVAL_LABEL).map(([k, v]) => ({ value: k, label: v }))} />
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: '员工', render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: '日期', dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: '时长', dataIndex: 'hours' },
          { title: '事由', dataIndex: 'reason' },
          { title: '状态', dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as ApprovalStatus]}>{APPROVAL_LABEL[v as ApprovalStatus]}</Tag> },
          {
            title: '操作',
            render: (_, r: any) =>
              r.status === 'PENDING' ? (
                <Space>
                  <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                    通过
                  </Button>
                  <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                    驳回
                  </Button>
                </Space>
              ) : null,
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? '通过申请' : '驳回申请'}
        open={!!modal}
        onCancel={() => setModal(null)}
        onOk={() => mutation.mutate()}
        confirmLoading={mutation.isPending}
      >
        <Input.TextArea rows={3} placeholder="审批意见（可选）" value={comment} onChange={(e) => setComment(e.target.value)} />
      </Modal>
    </>
  );
}

export default function Approval() {
  return (
    <div>
      <Typography.Title level={3}>待审批列表</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'leave', label: '请假申请', children: <LeaveApprovalTab /> },
            { key: 'overtime', label: '加班申请', children: <OvertimeApprovalTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
