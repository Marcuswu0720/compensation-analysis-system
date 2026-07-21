import { Button, Card, DatePicker, Form, Input, Popconfirm, Select, Table, Tag, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { specialEventsApi } from '../api/specialEvents';
import { officesApi } from '../api/org';
import { useEventTypeLabel } from '../utils/status';

export default function SpecialEvents() {
  const { t } = useTranslation();
  const eventTypeLabel = useEventTypeLabel();
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
      message.success(t('specialEvents.createSuccess'));
      queryClient.invalidateQueries({ queryKey: ['special-events'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('specialEvents.createFailed')),
  });

  const revokeMutation = useMutation({
    mutationFn: specialEventsApi.revoke,
    onSuccess: () => {
      message.success(t('specialEvents.revokeSuccess'));
      queryClient.invalidateQueries({ queryKey: ['special-events'] });
    },
  });

  return (
    <div>
      <Typography.Title level={3}>{t('specialEvents.title')}</Typography.Title>
      <Card title={t('specialEvents.createTitle')} style={{ marginBottom: 16 }}>
        <Form layout="vertical" onFinish={(v) => createMutation.mutate(v)} style={{ maxWidth: 480 }}>
          <Form.Item name="type" label={t('specialEvents.eventType')} rules={[{ required: true }]}>
            <Select
              placeholder={t('specialEvents.eventType')}
              options={[
                { value: 'EXTREME_WEATHER', label: t('specialEvents.extremeWeather') },
                { value: 'EMERGENCY_EVENT', label: t('specialEvents.emergencyEvent') },
              ]}
            />
          </Form.Item>
          <Form.Item name="affectedOfficeIds" label={t('specialEvents.affectedOffices')} rules={[{ required: true }]}>
            <Select mode="multiple" placeholder={t('specialEvents.affectedOffices')} options={offices.map((o) => ({ value: o.id, label: o.name }))} />
          </Form.Item>
          <Form.Item name="range" label={t('specialEvents.effectivePeriod')} rules={[{ required: true }]}>
            <DatePicker.RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label={t('specialEvents.remark')}>
            <Input placeholder={t('specialEvents.remark')} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
            {t('specialEvents.createAndMark')}
          </Button>
        </Form>
      </Card>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={events}
        columns={[
          { title: t('specialEvents.typeCol'), dataIndex: 'type', render: (v) => eventTypeLabel[v as keyof typeof eventTypeLabel] },
          { title: t('specialEvents.affectedOfficesCol'), dataIndex: 'affectedOffices', render: (v: any[]) => v.map((x) => x.office.name).join(', ') },
          { title: t('specialEvents.startTimeCol'), dataIndex: 'startTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: t('specialEvents.endTimeCol'), dataIndex: 'endTime', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          { title: t('specialEvents.remark'), dataIndex: 'remark' },
          {
            title: t('specialEvents.statusCol'),
            render: (_, r: any) => (r.revokedAt ? <Tag color="default">{t('specialEvents.revoked')}</Tag> : <Tag color="green">{t('specialEvents.inEffect')}</Tag>),
          },
          {
            title: t('common.actions'),
            render: (_, r: any) =>
              !r.revokedAt ? (
                <Popconfirm title={t('specialEvents.revokeConfirm')} onConfirm={() => revokeMutation.mutate(r.id)}>
                  <Button size="small" danger>
                    {t('common.revoke')}
                  </Button>
                </Popconfirm>
              ) : null,
          },
        ]}
      />
    </div>
  );
}
