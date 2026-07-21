import { useState } from 'react';
import { Badge, Calendar, Card, Descriptions, Empty, Modal, Space, Typography, DatePicker } from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { attendanceApi } from '../api/attendance';
import { useStatusLabel } from '../utils/status';
import type { AttendanceRecord } from '../api/types';

const BADGE_STATUS: Record<string, 'success' | 'warning' | 'error' | 'processing' | 'default'> = {
  NORMAL: 'success',
  LATE: 'warning',
  EARLY_LEAVE: 'warning',
  ABSENT: 'error',
  LEAVE: 'processing',
  FULL_ATTENDANCE: 'success',
  PENDING: 'default',
  UNCONFIGURED: 'error',
};

export default function MyAttendance() {
  const { t } = useTranslation();
  const statusLabel = useStatusLabel();
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [detail, setDetail] = useState<AttendanceRecord | null>(null);
  const [detailDate, setDetailDate] = useState<string | null>(null);

  const { data: records = [] } = useQuery({
    queryKey: ['attendance-calendar', month.format('YYYY-MM')],
    queryFn: () => attendanceApi.myCalendar(month.format('YYYY-MM')),
  });

  const byDate = new Map(records.map((r) => [dayjs(r.date).format('YYYY-MM-DD'), r]));

  // 一天可能同时有"上班"和"下班"两条独立状态，不能只用单一 status 字段覆盖显示（问题反馈 2.3）
  function dayBadges(record: AttendanceRecord): { key: string; status: keyof typeof BADGE_STATUS; text: string }[] {
    const wholeDayStatuses = ['LEAVE', 'FULL_ATTENDANCE', 'ABSENT', 'PENDING'];
    if (wholeDayStatuses.includes(record.status) || (!record.clockInAt && !record.clockOutAt)) {
      return [{ key: 'whole', status: record.status, text: statusLabel[record.status] }];
    }
    const badges: { key: string; status: keyof typeof BADGE_STATUS; text: string }[] = [];
    if (record.clockInAt) {
      if (record.status === 'UNCONFIGURED') {
        badges.push({ key: 'in', status: 'UNCONFIGURED', text: t('myAttendance.badgeInUnconfigured') });
      } else {
        badges.push({ key: 'in', status: record.lateMinutes > 0 ? 'LATE' : 'NORMAL', text: `${t('myAttendance.badgeIn')}-${record.lateMinutes > 0 ? t('myAttendance.late') : t('myAttendance.onTime')}` });
      }
    }
    if (record.clockOutAt) {
      if (record.status === 'UNCONFIGURED') {
        badges.push({ key: 'out', status: 'UNCONFIGURED', text: t('myAttendance.badgeOutUnconfigured') });
      } else {
        badges.push({ key: 'out', status: record.earlyMinutes > 0 ? 'EARLY_LEAVE' : 'NORMAL', text: `${t('myAttendance.badgeOut')}-${record.earlyMinutes > 0 ? t('myAttendance.early') : t('myAttendance.onTime')}` });
      }
    }
    return badges;
  }

  const handleSelect = (date: Dayjs) => {
    const key = date.format('YYYY-MM-DD');
    const record = byDate.get(key) ?? null;
    setDetail(record);
    setDetailDate(key);
  };

  return (
    <div>
      <Typography.Title level={3}>{t('myAttendance.title')}</Typography.Title>
      <Card>
        <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} style={{ marginBottom: 16 }} />
        <Calendar
          value={month}
          // 年视图下点选月份、月视图下翻页/切月，都需要同步更新，否则会一直停在当前月不动（问题反馈 2.4）
          onPanelChange={(v) => setMonth(v)}
          onChange={(v) => setMonth(v)}
          onSelect={handleSelect}
          fullscreen={false}
          cellRender={(date) => {
            const record = byDate.get(date.format('YYYY-MM-DD'));
            if (!record) return null;
            return (
              <Space direction="vertical" size={0}>
                {dayBadges(record).map((b) => (
                  <Badge key={b.key} status={BADGE_STATUS[b.status]} text={<span style={{ fontSize: 12 }}>{b.text}</span>} />
                ))}
              </Space>
            );
          }}
        />
      </Card>

      <Modal title={t('myAttendance.detailTitle', { date: detailDate })} open={!!detailDate} onCancel={() => setDetailDate(null)} footer={null}>
        {detail ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t('myAttendance.clockInTime')}>{detail.clockInAt ? dayjs(detail.clockInAt).format('HH:mm:ss') : t('myAttendance.notClockedIn')}</Descriptions.Item>
            <Descriptions.Item label={t('myAttendance.clockOutTime')}>{detail.clockOutAt ? dayjs(detail.clockOutAt).format('HH:mm:ss') : t('myAttendance.notClockedIn')}</Descriptions.Item>
            <Descriptions.Item label={t('myAttendance.lateMinutes')}>{detail.lateMinutes}</Descriptions.Item>
            <Descriptions.Item label={t('myAttendance.earlyMinutes')}>{detail.earlyMinutes}</Descriptions.Item>
            {detail.matchedOffice && <Descriptions.Item label={t('myAttendance.location')}>{detail.matchedOffice.name}</Descriptions.Item>}
            {detail.clockInLat != null && detail.clockInLng != null && (
              <Descriptions.Item label={t('myAttendance.coordinates')}>
                {detail.clockInLat.toFixed(4)}, {detail.clockInLng.toFixed(4)}
              </Descriptions.Item>
            )}
            {detail.remark && <Descriptions.Item label={t('myAttendance.remark')}>{detail.remark}</Descriptions.Item>}
          </Descriptions>
        ) : (
          <Empty description={t('myAttendance.noRecord')} />
        )}
      </Modal>
    </div>
  );
}
