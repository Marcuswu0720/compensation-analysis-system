import { Button, Card, Popconfirm, Table, Tabs, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { leaveApi, overtimeApi } from '../../api/leaveOvertime';
import { APPROVAL_COLOR, APPROVAL_LABEL } from '../../utils/status';

function LeaveTab() {
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['my-leave'], queryFn: leaveApi.mine });
  const cancelMutation = useMutation({
    mutationFn: leaveApi.cancel,
    onSuccess: () => {
      message.success('已撤销');
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
        { title: '类型', dataIndex: ['type', 'name'] },
        { title: '开始时间', dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
        { title: '结束时间', dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
        { title: '事由', dataIndex: 'reason' },
        { title: '状态', dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as keyof typeof APPROVAL_COLOR]}>{APPROVAL_LABEL[v as keyof typeof APPROVAL_LABEL]}</Tag> },
        { title: '审批意见', dataIndex: 'approveComment' },
        {
          title: '操作',
          render: (_, record) =>
            record.status === 'PENDING' ? (
              <Popconfirm title="确认撤销该申请？" onConfirm={() => cancelMutation.mutate(record.id)}>
                <Button size="small" danger>
                  撤销
                </Button>
              </Popconfirm>
            ) : null,
        },
      ]}
    />
  );
}

function OvertimeTab() {
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['my-overtime'], queryFn: overtimeApi.mine });
  const cancelMutation = useMutation({
    mutationFn: overtimeApi.cancel,
    onSuccess: () => {
      message.success('已撤销');
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
        { title: '日期', dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
        { title: '时长(小时)', dataIndex: 'hours' },
        { title: '事由', dataIndex: 'reason' },
        { title: '状态', dataIndex: 'status', render: (v) => <Tag color={APPROVAL_COLOR[v as keyof typeof APPROVAL_COLOR]}>{APPROVAL_LABEL[v as keyof typeof APPROVAL_LABEL]}</Tag> },
        { title: '审批意见', dataIndex: 'approveComment' },
        {
          title: '操作',
          render: (_, record) =>
            record.status === 'PENDING' ? (
              <Popconfirm title="确认撤销该申请？" onConfirm={() => cancelMutation.mutate(record.id)}>
                <Button size="small" danger>
                  撤销
                </Button>
              </Popconfirm>
            ) : null,
        },
      ]}
    />
  );
}

export default function MyApplications() {
  return (
    <div>
      <Typography.Title level={3}>我的申请记录</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'leave', label: '请假申请', children: <LeaveTab /> },
            { key: 'overtime', label: '加班申请', children: <OvertimeTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
