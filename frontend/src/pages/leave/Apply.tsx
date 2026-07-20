import { Button, Card, DatePicker, Form, Input, InputNumber, Select, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery } from '@tanstack/react-query';
import { leaveApi, overtimeApi } from '../../api/leaveOvertime';

export default function LeaveApply() {
  const { data: leaveTypes = [] } = useQuery({ queryKey: ['leave-types'], queryFn: () => leaveApi.types(true) });

  const leaveMutation = useMutation({
    mutationFn: (values: any) =>
      leaveApi.apply({
        typeId: values.typeId,
        startTime: values.range[0].toISOString(),
        endTime: values.range[1].toISOString(),
        reason: values.reason,
      }),
    onSuccess: () => message.success('请假申请已提交'),
    onError: (e: any) => message.error(e?.response?.data?.message ?? '提交失败'),
  });

  const overtimeMutation = useMutation({
    mutationFn: (values: any) =>
      overtimeApi.apply({ date: values.date.format('YYYY-MM-DD'), hours: values.hours, reason: values.reason }),
    onSuccess: () => message.success('加班申请已提交'),
    onError: (e: any) => message.error(e?.response?.data?.message ?? '提交失败'),
  });

  return (
    <div style={{ maxWidth: 560 }}>
      <Typography.Title level={3}>请假/加班申请</Typography.Title>
      <Card>
        <Tabs
          items={[
            {
              key: 'leave',
              label: '请假申请',
              children: (
                <Form layout="vertical" onFinish={(v) => leaveMutation.mutate(v)}>
                  <Form.Item name="typeId" label="请假类型" rules={[{ required: true }]}>
                    <Select options={leaveTypes.map((t) => ({ label: t.name, value: t.id }))} placeholder="请选择请假类型" />
                  </Form.Item>
                  <Form.Item name="range" label="请假时间段" rules={[{ required: true }]}>
                    <DatePicker.RangePicker showTime style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="reason" label="事由说明" rules={[{ required: true }]}>
                    <Input.TextArea rows={3} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={leaveMutation.isPending}>
                    提交请假申请
                  </Button>
                </Form>
              ),
            },
            {
              key: 'overtime',
              label: '加班申请',
              children: (
                <Form layout="vertical" onFinish={(v) => overtimeMutation.mutate(v)}>
                  <Form.Item name="date" label="加班日期" rules={[{ required: true }]}>
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="hours" label="加班时长（小时）" rules={[{ required: true }]}>
                    <InputNumber min={0.5} step={0.5} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="reason" label="事由说明" rules={[{ required: true }]}>
                    <Input.TextArea rows={3} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={overtimeMutation.isPending}>
                    提交加班申请
                  </Button>
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
