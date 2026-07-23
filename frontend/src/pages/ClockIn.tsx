import { useState } from 'react';
import { Alert, Button, Card, DatePicker, Empty, Image, Space, Typography, Upload, InputNumber, message, Descriptions } from 'antd';
import { UploadOutlined, EnvironmentOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs, { type Dayjs } from 'dayjs';
import { attendanceApi } from '../api/attendance';
import { locationCheckinApi } from '../api/locationCheckin';
import { STATUS_COLOR, VERIFY_COLOR, useStatusLabel, useModeLabel, useVerifyLabel } from '../utils/status';
import { PHOTO_FALLBACK } from '../utils/imagePlaceholder';
import { useAuthStore } from '../store/authStore';
import { Tag } from 'antd';

const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000/api').replace(/\/api\/?$/, '');

export default function ClockIn() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const { t } = useTranslation();
  const statusLabel = useStatusLabel();
  const modeLabel = useModeLabel();
  const verifyLabel = useVerifyLabel();
  const [businessMetric, setBusinessMetric] = useState<number | null>(null);
  const [trajectoryDate, setTrajectoryDate] = useState<Dayjs>(dayjs());

  function getGeolocation(): Promise<{ lat: number; lng: number }> {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error(t('clockIn.geoNotSupported')));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => reject(new Error(t('clockIn.geoFailed'))),
        { enableHighAccuracy: true, timeout: 10000 },
      );
    });
  }

  const { data: today, refetch } = useQuery({ queryKey: ['attendance-today'], queryFn: attendanceApi.today });
  // 员工本人查看自己的定位打卡照片轨迹（问题反馈 4.3：之前只能看到全勤/异常，看不到自己实际拍过的照片）
  const { data: myPhotos = [] } = useQuery({
    queryKey: ['my-location-trajectory', trajectoryDate.format('YYYY-MM-DD')],
    queryFn: () => locationCheckinApi.trajectory(user!.id, trajectoryDate.format('YYYY-MM-DD')),
    enabled: !!user,
  });

  const clockInMutation = useMutation({
    mutationFn: async () => {
      let coords: { lat: number; lng: number } | undefined;
      try {
        coords = await getGeolocation();
      } catch {
        coords = undefined;
      }
      return attendanceApi.clockIn(coords);
    },
    onSuccess: (record) => {
      message.success(record.matchedOffice ? t('clockIn.clockInSuccessWithOffice', { office: record.matchedOffice.name }) : t('clockIn.clockInSuccess'));
      refetch();
      queryClient.invalidateQueries({ queryKey: ['attendance-calendar'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('clockIn.clockFailed')),
  });

  const clockOutMutation = useMutation({
    mutationFn: async () => {
      let coords: { lat: number; lng: number } | undefined;
      try {
        coords = await getGeolocation();
      } catch {
        coords = undefined;
      }
      return attendanceApi.clockOut(coords);
    },
    onSuccess: () => {
      message.success(t('clockIn.clockOutSuccess'));
      refetch();
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('clockIn.clockFailed')),
  });

  const photoUploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const coords = await getGeolocation();
      return locationCheckinApi.upload({ photo: file, lat: coords.lat, lng: coords.lng, businessMetricValue: businessMetric ?? undefined });
    },
    onSuccess: () => {
      message.success(t('clockIn.uploadSuccess'));
      queryClient.invalidateQueries({ queryKey: ['my-location-trajectory'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('clockIn.uploadFailed')),
  });

  const rule = today?.effectiveRule;

  return (
    <div style={{ maxWidth: 640 }}>
      <Typography.Title level={3}>{t('clockIn.title')}</Typography.Title>
      <Card>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label={t('clockIn.todayDate')}>{dayjs().format('YYYY-MM-DD dddd')}</Descriptions.Item>
          {rule?.mode && <Descriptions.Item label={t('clockIn.mode')}>{modeLabel[rule.mode as keyof typeof modeLabel]}</Descriptions.Item>}
          <Descriptions.Item label={t('clockIn.todayStatus')}>
            {today?.record ? (
              <Tag color={STATUS_COLOR[today.record.status as keyof typeof STATUS_COLOR]}>
                {statusLabel[today.record.status as keyof typeof statusLabel]}
              </Tag>
            ) : (
              <Tag>{t('clockIn.noRecord')}</Tag>
            )}
          </Descriptions.Item>
          {today?.record?.clockInAt && <Descriptions.Item label={t('clockIn.clockInTime')}>{dayjs(today.record.clockInAt).format('HH:mm:ss')}</Descriptions.Item>}
          {today?.record?.matchedOffice && (
            <Descriptions.Item label={t('clockIn.matchedOffice')}>{today.record.matchedOffice.name}</Descriptions.Item>
          )}
          {today?.record?.clockOutAt && <Descriptions.Item label={t('clockIn.clockOutTime')}>{dayjs(today.record.clockOutAt).format('HH:mm:ss')}</Descriptions.Item>}
        </Descriptions>

        <div style={{ marginTop: 24 }}>
          {rule && !rule.requiresPhoto && (
            <Space size="large">
              {rule.requiresClockIn && (
                <Button type="primary" size="large" onClick={() => clockInMutation.mutate()} loading={clockInMutation.isPending} disabled={!!today?.record?.clockInAt}>
                  {t('clockIn.clockInBtn')}
                </Button>
              )}
              {rule.requiresClockOut && (
                <Button size="large" onClick={() => clockOutMutation.mutate()} loading={clockOutMutation.isPending} disabled={!today?.record?.clockInAt || !!today?.record?.clockOutAt}>
                  {t('clockIn.clockOutBtn')}
                </Button>
              )}
            </Space>
          )}

          {rule?.requiresPhoto && (
            <div>
              <Alert
                type="info"
                showIcon
                icon={<EnvironmentOutlined />}
                message={t('clockIn.photoModeTitle')}
                description={t('clockIn.photoModeDesc')}
                style={{ marginBottom: 16 }}
              />
              {rule.requiresBusinessMetric && (
                <div style={{ marginBottom: 16 }}>
                  <span style={{ marginRight: 8 }}>{t('clockIn.businessMetricLabel')}</span>
                  <InputNumber min={0} value={businessMetric ?? undefined} onChange={(v) => setBusinessMetric(v)} />
                </div>
              )}
              <Upload
                showUploadList={false}
                accept="image/*"
                capture="environment"
                customRequest={({ file }) => photoUploadMutation.mutate(file as File)}
              >
                <Button icon={<UploadOutlined />} loading={photoUploadMutation.isPending}>
                  {t('clockIn.uploadBtn')}
                </Button>
              </Upload>
            </div>
          )}
        </div>
      </Card>

      {rule?.requiresPhoto && (
        <Card title={t('clockIn.myTrajectoryTitle')} style={{ marginTop: 16 }}>
          <DatePicker value={trajectoryDate} onChange={(v) => v && setTrajectoryDate(v)} style={{ marginBottom: 16 }} />
          {myPhotos.length === 0 ? (
            <Empty description={t('clockIn.noPhotosToday')} />
          ) : (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {myPhotos.map((photo, idx) => (
                <Card key={photo.id} size="small" style={{ width: 160 }} title={`#${idx + 1} ${dayjs(photo.takenAt).format('HH:mm:ss')}`}>
                  <Image src={`${API_ORIGIN}${photo.photoUrl}`} width={136} fallback={PHOTO_FALLBACK} />
                  <div style={{ marginTop: 8 }}>
                    <Tag color={VERIFY_COLOR[photo.verifyStatus]}>{verifyLabel[photo.verifyStatus]}</Tag>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
