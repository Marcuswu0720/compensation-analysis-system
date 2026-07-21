import { Button, Card, DatePicker, Form, Input, InputNumber, Select, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { leaveApi, overtimeApi } from '../../api/leaveOvertime';

export default function LeaveApply() {
  const { t } = useTranslation();
  const { data: leaveTypes = [] } = useQuery({ queryKey: ['leave-types'], queryFn: () => leaveApi.types(true) });

  const leaveMutation = useMutation({
    mutationFn: (values: any) =>
      leaveApi.apply({
        typeId: values.typeId,
        startTime: values.range[0].toISOString(),
        endTime: values.range[1].toISOString(),
        reason: values.reason,
      }),
    onSuccess: () => message.success(t('leaveApply.leaveSubmitted')),
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('common.submitFailed')),
  });

  const overtimeMutation = useMutation({
    mutationFn: (values: any) =>
      overtimeApi.apply({ date: values.date.format('YYYY-MM-DD'), hours: values.hours, reason: values.reason }),
    onSuccess: () => message.success(t('leaveApply.overtimeSubmitted')),
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('common.submitFailed')),
  });

  return (
    <div style={{ maxWidth: 560 }}>
      <Typography.Title level={3}>{t('leaveApply.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            {
              key: 'leave',
              label: t('leaveApply.leaveTab'),
              children: (
                <Form layout="vertical" onFinish={(v) => leaveMutation.mutate(v)}>
                  <Form.Item name="typeId" label={t('leaveApply.leaveType')} rules={[{ required: true }]}>
                    <Select options={leaveTypes.map((lt) => ({ label: lt.name, value: lt.id }))} placeholder={t('leaveApply.leaveTypePlaceholder')} />
                  </Form.Item>
                  <Form.Item name="range" label={t('leaveApply.leavePeriod')} rules={[{ required: true }]}>
                    <DatePicker.RangePicker showTime style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="reason" label={t('leaveApply.reason')} rules={[{ required: true }]}>
                    <Input.TextArea rows={3} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={leaveMutation.isPending}>
                    {t('leaveApply.submitLeave')}
                  </Button>
                </Form>
              ),
            },
            {
              key: 'overtime',
              label: t('leaveApply.overtimeTab'),
              children: (
                <Form layout="vertical" onFinish={(v) => overtimeMutation.mutate(v)}>
                  <Form.Item name="date" label={t('leaveApply.overtimeDate')} rules={[{ required: true }]}>
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="hours" label={t('leaveApply.overtimeHours')} rules={[{ required: true }]}>
                    <InputNumber min={0.5} step={0.5} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="reason" label={t('leaveApply.reason')} rules={[{ required: true }]}>
                    <Input.TextArea rows={3} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={overtimeMutation.isPending}>
                    {t('leaveApply.submitOvertime')}
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
