import { useState } from 'react';
import { Badge, Calendar, Card, Descriptions, Empty, Modal, Space, Typography, DatePicker } from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import { attendanceApi } from '../api/attendance';
import { STATUS_LABEL } from '../utils/status';
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

// 一天可能同时有"上班"和"下班"两条独立状态，不能只用单一 status 字段覆盖显示（问题反馈 2.3）
function dayBadges(record: AttendanceRecord): { key: string; status: keyof typeof BADGE_STATUS; text: string }[] {
  const wholeDayStatuses = ['LEAVE', 'FULL_ATTENDANCE', 'ABSENT', 'PENDING'];
  if (wholeDayStatuses.includes(record.status) || (!record.clockInAt && !record.clockOutAt)) {
    return [{ key: 'whole', status: record.status, text: STATUS_LABEL[record.status] }];
  }
  const badges: { key: string; status: keyof typeof BADGE_STATUS; text: string }[] = [];
  if (record.clockInAt) {
    if (record.status === 'UNCONFIGURED') {
      badges.push({ key: 'in', status: 'UNCONFIGURED', text: '上班-未配置规则' });
    } else {
      badges.push({ key: 'in', status: record.lateMinutes > 0 ? 'LATE' : 'NORMAL', text: `上班-${record.lateMinutes > 0 ? '迟到' : '正常'}` });
    }
  }
  if (record.clockOutAt) {
    if (record.status === 'UNCONFIGURED') {
      badges.push({ key: 'out', status: 'UNCONFIGURED', text: '下班-未配置规则' });
    } else {
      badges.push({ key: 'out', status: record.earlyMinutes > 0 ? 'EARLY_LEAVE' : 'NORMAL', text: `下班-${record.earlyMinutes > 0 ? '早退' : '正常'}` });
    }
  }
  return badges;
}

export default function MyAttendance() {
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [detail, setDetail] = useState<AttendanceRecord | null>(null);
  const [detailDate, setDetailDate] = useState<string | null>(null);

  const { data: records = [] } = useQuery({
    queryKey: ['attendance-calendar', month.format('YYYY-MM')],
    queryFn: () => attendanceApi.myCalendar(month.format('YYYY-MM')),
  });

  const byDate = new Map(records.map((r) => [dayjs(r.date).format('YYYY-MM-DD'), r]));

  const handleSelect = (date: Dayjs) => {
    const key = date.format('YYYY-MM-DD');
    const record = byDate.get(key) ?? null;
    setDetail(record);
    setDetailDate(key);
  };

  return (
    <div>
      <Typography.Title level={3}>个人考勤日历</Typography.Title>
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

      <Modal title={`${detailDate} 考勤明细`} open={!!detailDate} onCancel={() => setDetailDate(null)} footer={null}>
        {detail ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="上班打卡时间">{detail.clockInAt ? dayjs(detail.clockInAt).format('HH:mm:ss') : '未打卡'}</Descriptions.Item>
            <Descriptions.Item label="下班打卡时间">{detail.clockOutAt ? dayjs(detail.clockOutAt).format('HH:mm:ss') : '未打卡'}</Descriptions.Item>
            <Descriptions.Item label="迟到分钟数">{detail.lateMinutes}</Descriptions.Item>
            <Descriptions.Item label="早退分钟数">{detail.earlyMinutes}</Descriptions.Item>
            {detail.matchedOffice && <Descriptions.Item label="打卡地点">{detail.matchedOffice.name}</Descriptions.Item>}
            {detail.clockInLat != null && detail.clockInLng != null && (
              <Descriptions.Item label="定位坐标">
                {detail.clockInLat.toFixed(4)}, {detail.clockInLng.toFixed(4)}
              </Descriptions.Item>
            )}
            {detail.remark && <Descriptions.Item label="备注">{detail.remark}</Descriptions.Item>}
          </Descriptions>
        ) : (
          <Empty description="当天无打卡记录" />
        )}
      </Modal>
    </div>
  );
}
