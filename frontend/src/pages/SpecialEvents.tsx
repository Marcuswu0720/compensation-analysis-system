import { Button, Card, DatePicker, Form, Input, Popconfirm, Select, Table, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { specialEventsApi } from '../api/specialEvents';
import { officesApi } from '../api/org';
import { EVENT_TYPE_LABEL } from '../utils/status';

export default function SpecialEvents() {
  const queryClient = useQueryClient();
  const { data: events = [] } = useQuery({ queryKey: ['special-events'], queryFn: specialEventsApi.list });
  const { data: offices = [] } = useQuery({ queryKey: ['offices'], queryFn: officesApi.list });

  const createMutation = useMutation({
    mutationFn: (values: any) =>
      specialEventsApi.create({
        type: values.type,
        affectedOfficeIds: values.affectedOfficeIds,
        startTime: values.range[0].toISOString(),
        endTime: values.range[1].toISOString(),
        remark: values.remark,
      }),
    onSuccess: () => {
      message.success('已创建，受影响员工已自动标记全勤');
      queryClient.invalidateQueries({ queryKey: ['special-events'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '创建失败'),
  });

  const revokeMutation = useMutation({
    mutationFn: specialEventsApi.revoke,
    onSuccess: () => {
      message.success('已撤销');
      queryClient.invalidateQueries({ queryKey: ['special-events'] });
    },
  });

  return (
    <div>
      <Typography.Title level={3}>特殊事件标记（极端天气 / 突发事件）</Typography.Title>
      <Card title="新建标记" style={{ marginBottom: 16 }}>
        <Form layout="vertical" onFinish={(v) => createMutation.mutate(v)} style={{ maxWidth: 480 }}>
          <Form.Item name="type" label="事件类型" rules={[{ required: true }]}>
            <Select
              placeholder="事件类型"
              options={[
                { value: 'EXTREME_WEATHER', label: '极端天气' },
                { value: 'EMERGENCY_EVENT', label: '突发事件' },
              ]}
            />
          </Form.Item>
          <Form.Item name="affectedOfficeIds" label="受影响办公室" rules={[{ required: true }]}>
            <Select mode="multiple" placeholder="受影响办公室" options={offices.map((o) => ({ value: o.id, label: o.name }))} />
          </Form.Item>
          <Form.Item name="range" label="生效时间段" rules={[{ required: true }]}>
            <DatePicker.RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input placeholder="备注" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
            创建并自动标记全勤
          </Button>
        </Form>
      </Card>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={events}
        columns={[
          { title: '类型', dataIndex: 'type', render: (v) => EVENT_TYPE_LABEL[v as keyof typeof EVENT_TYPE_LABEL] },
          { title: '受影响办公室', dataIndex: 'affectedOffices', render: (v: any[]) => v.map((x) => x.office.name).join(', ') },
          { title: '开始时间', dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: '结束时间', dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: '备注', dataIndex: 'remark' },
          {
            title: '状态',
            render: (_, r: any) => (r.revokedAt ? <Tag color="default">已撤销</Tag> : <Tag color="green">生效中</Tag>),
          },
          {
            title: '操作',
            render: (_, r: any) =>
              !r.revokedAt ? (
                <Popconfirm title="确认撤销该标记？未打卡的自动全勤记录将回退" onConfirm={() => revokeMutation.mutate(r.id)}>
                  <Button size="small" danger>
                    撤销
                  </Button>
                </Popconfirm>
              ) : null,
          },
        ]}
      />
    </div>
  );
}
