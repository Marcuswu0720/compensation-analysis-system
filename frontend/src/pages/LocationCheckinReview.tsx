import { useState } from 'react';
import { Button, Card, Image, Input, Modal, Space, Table, Tabs, Tag, Typography, message, DatePicker, Select } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { locationCheckinApi } from '../api/locationCheckin';
import { usersApi } from '../api/org';
import { VERIFY_COLOR, useVerifyLabel } from '../utils/status';
import { PHOTO_FALLBACK } from '../utils/imagePlaceholder';

const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000/api').replace(/\/api\/?$/, '');

function PendingTab() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ['location-pending'], queryFn: locationCheckinApi.pending });
  const [modal, setModal] = useState<{ id: string; status: 'APPROVED' | 'REJECTED' } | null>(null);
  const [remark, setRemark] = useState('');

  const mutation = useMutation({
    mutationFn: () => locationCheckinApi.verify(modal!.id, modal!.status, remark),
    onSuccess: () => {
      message.success(t('locationCheckinReview.verified'));
      setModal(null);
      setRemark('');
      queryClient.invalidateQueries({ queryKey: ['location-pending'] });
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.message ?? t('common.opFailed'));
      queryClient.invalidateQueries({ queryKey: ['location-pending'] });
    },
  });

  return (
    <>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: t('locationCheckinReview.photo'), dataIndex: 'photoUrl', render: (v) => <Image src={`${API_ORIGIN}${v}`} width={80} fallback={PHOTO_FALLBACK} /> },
          { title: t('common.employee'), render: (_, r: any) => `${r.user?.name}(${r.user?.employeeNo})` },
          { title: t('common.team'), render: (_, r: any) => r.user?.team?.name },
          { title: t('locationCheckinReview.takenAt'), dataIndex: 'takenAt', render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm:ss') },
          { title: t('locationCheckinReview.gps'), render: (_, r: any) => `${r.gpsLat.toFixed(4)}, ${r.gpsLng.toFixed(4)}` },
          { title: t('locationCheckinReview.businessMetric'), dataIndex: 'businessMetricValue' },
          {
            title: t('locationCheckinReview.withinRange'),
            dataIndex: 'isWithinRange',
            render: (v: boolean | null) =>
              v === null ? (
                <Tag>{t('locationCheckinReview.rangeNotApplicable')}</Tag>
              ) : v ? (
                <Tag color="green">{t('locationCheckinReview.withinRangeYes')}</Tag>
              ) : (
                <Tag color="red">{t('locationCheckinReview.withinRangeNo')}</Tag>
              ),
          },
          {
            title: t('common.actions'),
            render: (_, r: any) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setModal({ id: r.id, status: 'APPROVED' })}>
                  {t('common.approve')}
                </Button>
                <Button size="small" danger onClick={() => setModal({ id: r.id, status: 'REJECTED' })}>
                  {t('common.reject')}
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal title={t('locationCheckinReview.verifyTitle')} open={!!modal} onCancel={() => setModal(null)} onOk={() => mutation.mutate()} confirmLoading={mutation.isPending}>
        <Input.TextArea rows={3} placeholder={t('common.remarkOptional')} value={remark} onChange={(e) => setRemark(e.target.value)} />
      </Modal>
    </>
  );
}

function TrajectoryTab() {
  const { t } = useTranslation();
  const verifyLabel = useVerifyLabel();
  const [userId, setUserId] = useState<string>();
  const [date, setDate] = useState(dayjs());
  const { data: users = [] } = useQuery({ queryKey: ['users-all'], queryFn: () => usersApi.list() });
  const { data = [] } = useQuery({
    queryKey: ['trajectory', userId, date.format('YYYY-MM-DD')],
    queryFn: () => locationCheckinApi.trajectory(userId!, date.format('YYYY-MM-DD')),
    enabled: !!userId,
  });

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 240 }}
          placeholder={t('locationCheckinReview.selectEmployee')}
          value={userId}
          onChange={setUserId}
          options={users.map((u) => ({ value: u.id, label: `${u.name}(${u.employeeNo})` }))}
          showSearch
          filterOption={(input, option) => (option?.label as string).toLowerCase().includes(input.toLowerCase())}
        />
        <DatePicker value={date} onChange={(v) => v && setDate(v)} />
      </Space>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {data.map((photo, idx) => (
          <Card key={photo.id} size="small" style={{ width: 180 }} title={`#${idx + 1} ${dayjs(photo.takenAt).format('HH:mm:ss')}`}>
            <Image src={`${API_ORIGIN}${photo.photoUrl}`} width={150} fallback={PHOTO_FALLBACK} />
            <div style={{ marginTop: 8 }}>
              <Tag color={VERIFY_COLOR[photo.verifyStatus]}>{verifyLabel[photo.verifyStatus]}</Tag>
              {photo.isWithinRange !== null && (
                <Tag color={photo.isWithinRange ? 'green' : 'red'}>
                  {photo.isWithinRange ? t('locationCheckinReview.withinRangeYes') : t('locationCheckinReview.withinRangeNo')}
                </Tag>
              )}
            </div>
            <div style={{ fontSize: 12, color: '#888' }}>
              {photo.gpsLat.toFixed(4)}, {photo.gpsLng.toFixed(4)}
            </div>
          </Card>
        ))}
        {userId && data.length === 0 && <Typography.Text type="secondary">{t('locationCheckinReview.noPhotosToday')}</Typography.Text>}
      </div>
    </div>
  );
}

export default function LocationCheckinReview() {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={3}>{t('locationCheckinReview.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'pending', label: t('locationCheckinReview.pendingTab'), children: <PendingTab /> },
            { key: 'trajectory', label: t('locationCheckinReview.trajectoryTab'), children: <TrajectoryTab /> },
          ]}
        />
      </Card>
    </div>
  );
}
