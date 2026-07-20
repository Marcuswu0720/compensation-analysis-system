import { useState } from 'react';
import { Badge, Calendar, Card, Typography, DatePicker } from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import { attendanceApi } from '../api/attendance';
import { STATUS_LABEL, STATUS_COLOR } from '../utils/status';

const BADGE_STATUS: Record<string, 'success' | 'warning' | 'error' | 'processing' | 'default'> = {
  NORMAL: 'success',
  LATE: 'warning',
  EARLY_LEAVE: 'warning',
  ABSENT: 'error',
  LEAVE: 'processing',
  FULL_ATTENDANCE: 'success',
  PENDING: 'default',
};

export default function MyAttendance() {
  const [month, setMonth] = useState<Dayjs>(dayjs());

  const { data: records = [] } = useQuery({
    queryKey: ['attendance-calendar', month.format('YYYY-MM')],
    queryFn: () => attendanceApi.myCalendar(month.format('YYYY-MM')),
  });

  const byDate = new Map(records.map((r) => [dayjs(r.date).format('YYYY-MM-DD'), r]));

  return (
    <div>
      <Typography.Title level={3}>个人考勤日历</Typography.Title>
      <Card>
        <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} style={{ marginBottom: 16 }} />
        <Calendar
          value={month}
          onPanelChange={(v) => setMonth(v)}
          fullscreen={false}
          cellRender={(date) => {
            const record = byDate.get(date.format('YYYY-MM-DD'));
            if (!record) return null;
            return (
              <Badge
                status={BADGE_STATUS[record.status]}
                text={STATUS_LABEL[record.status]}
                style={{ fontSize: 12, color: STATUS_COLOR[record.status] === 'default' ? undefined : undefined }}
              />
            );
          }}
        />
      </Card>
    </div>
  );
}
