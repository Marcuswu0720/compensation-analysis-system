import { useState } from 'react';
import { Alert, Button, Card, Input, Modal, Space, Table, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { leaveApi, overtimeApi } from '../api/leaveOvertime';

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

function LeaveSpecialTab() {
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
        dataSource={data}
        locale={{ emptyText: '暂无待特批的请假申请' }}
        columns={[
          { title: '申请人', render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: '类型', dataIndex: ['type', 'name'] },
          { title: '开始', dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: '结束', dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: '事由', dataIndex: 'reason' },
          {
            title: '操作',
            render: (_, r: any) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                  特批通过
                </Button>
                <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                  特批驳回
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? '特批通过' : '特批驳回'}
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

function OvertimeSpecialTab() {
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
        dataSource={data}
        locale={{ emptyText: '暂无待特批的加班申请' }}
        columns={[
          { title: '申请人', render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: '日期', dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: '时长', dataIndex: 'hours' },
          { title: '事由', dataIndex: 'reason' },
          {
            title: '操作',
            render: (_, r: any) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setModal({ id: r.id, action: 'approve' })}>
                  特批通过
                </Button>
                <Button size="small" danger onClick={() => setModal({ id: r.id, action: 'reject' })}>
                  特批驳回
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={modal?.action === 'approve' ? '特批通过' : '特批驳回'}
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

export default function SpecialApproval() {
  return (
    <div>
      <Typography.Title level={3}>总部特批</Typography.Title>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="本地HR/HRIS 没有上级，其本人提交的请假/加班申请不能自己审批自己，统一路由到这里由总部特批（问题反馈 2.6）"
      />
      <Card>
        <Tabs
          items={[
            { key: 'leave', label: '请假申请', children: <LeaveSpecialTab /> },
            { key: 'overtime', label: '加班申请', children: <OvertimeSpecialTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
