import { useState } from 'react';
import { Alert, Button, Card, DatePicker, Empty, Image, Space, Typography, Upload, InputNumber, message, Descriptions } from 'antd';
import { UploadOutlined, EnvironmentOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs, { type Dayjs } from 'dayjs';
import { attendanceApi } from '../api/attendance';
import { locationCheckinApi } from '../api/locationCheckin';
import { STATUS_LABEL, STATUS_COLOR, MODE_LABEL, VERIFY_LABEL, VERIFY_COLOR } from '../utils/status';
import { useAuthStore } from '../store/authStore';
import { Tag } from 'antd';

const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:3000/api').replace(/\/api\/?$/, '');

function getGeolocation(): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('浏览器不支持定位'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => reject(new Error('获取定位失败，请检查浏览器定位权限')),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  });
}

export default function ClockIn() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [businessMetric, setBusinessMetric] = useState<number | null>(null);
  const [trajectoryDate, setTrajectoryDate] = useState<Dayjs>(dayjs());

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
      message.success(record.matchedOffice ? `上班打卡成功，已自动匹配最近办公室：${record.matchedOffice.name}` : '上班打卡成功');
      refetch();
      queryClient.invalidateQueries({ queryKey: ['attendance-calendar'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '打卡失败'),
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
      message.success('下班打卡成功');
      refetch();
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '打卡失败'),
  });

  const photoUploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const coords = await getGeolocation();
      return locationCheckinApi.upload({ photo: file, lat: coords.lat, lng: coords.lng, businessMetricValue: businessMetric ?? undefined });
    },
    onSuccess: () => {
      message.success('照片上传成功，等待核实');
      queryClient.invalidateQueries({ queryKey: ['my-location-trajectory'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '上传失败，请确认已授权定位权限'),
  });

  const rule = today?.effectiveRule;

  return (
    <div style={{ maxWidth: 640 }}>
      <Typography.Title level={3}>打卡</Typography.Title>
      <Card>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="今日日期">{dayjs().format('YYYY-MM-DD dddd')}</Descriptions.Item>
          {rule?.mode && <Descriptions.Item label="所属打卡模式">{MODE_LABEL[rule.mode as keyof typeof MODE_LABEL]}</Descriptions.Item>}
          <Descriptions.Item label="今日状态">
            {today?.record ? (
              <Tag color={STATUS_COLOR[today.record.status as keyof typeof STATUS_COLOR]}>
                {STATUS_LABEL[today.record.status as keyof typeof STATUS_LABEL]}
              </Tag>
            ) : (
              <Tag>暂无记录</Tag>
            )}
          </Descriptions.Item>
          {today?.record?.clockInAt && <Descriptions.Item label="上班打卡时间">{dayjs(today.record.clockInAt).format('HH:mm:ss')}</Descriptions.Item>}
          {today?.record?.matchedOffice && (
            <Descriptions.Item label="定位匹配办公室">{today.record.matchedOffice.name}</Descriptions.Item>
          )}
          {today?.record?.clockOutAt && <Descriptions.Item label="下班打卡时间">{dayjs(today.record.clockOutAt).format('HH:mm:ss')}</Descriptions.Item>}
        </Descriptions>

        <div style={{ marginTop: 24 }}>
          {rule && !rule.requiresPhoto && (
            <Space size="large">
              {rule.requiresClockIn && (
                <Button type="primary" size="large" onClick={() => clockInMutation.mutate()} loading={clockInMutation.isPending} disabled={!!today?.record?.clockInAt}>
                  上班打卡
                </Button>
              )}
              {rule.requiresClockOut && (
                <Button size="large" onClick={() => clockOutMutation.mutate()} loading={clockOutMutation.isPending} disabled={!today?.record?.clockInAt || !!today?.record?.clockOutAt}>
                  下班打卡
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
                message="该团队打卡方式为拍照+定位"
                description="请上传现场照片，系统将自动记录 GPS 坐标与拍摄时间，本地小管理者核实后计入考勤。"
                style={{ marginBottom: 16 }}
              />
              {rule.requiresBusinessMetric && (
                <div style={{ marginBottom: 16 }}>
                  <span style={{ marginRight: 8 }}>当日部署/拜访数量：</span>
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
                  拍照/上传照片打卡
                </Button>
              </Upload>
            </div>
          )}
        </div>
      </Card>

      {rule?.requiresPhoto && (
        <Card title="我的定位打卡记录" style={{ marginTop: 16 }}>
          <DatePicker value={trajectoryDate} onChange={(v) => v && setTrajectoryDate(v)} style={{ marginBottom: 16 }} />
          {myPhotos.length === 0 ? (
            <Empty description="当天暂无打卡照片" />
          ) : (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {myPhotos.map((photo, idx) => (
                <Card key={photo.id} size="small" style={{ width: 160 }} title={`#${idx + 1} ${dayjs(photo.takenAt).format('HH:mm:ss')}`}>
                  <Image src={`${API_ORIGIN}${photo.photoUrl}`} width={136} />
                  <div style={{ marginTop: 8 }}>
                    <Tag color={VERIFY_COLOR[photo.verifyStatus]}>{VERIFY_LABEL[photo.verifyStatus]}</Tag>
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
