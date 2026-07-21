import { useState } from 'react';
import { Button, Card, DatePicker, Select, Table, Typography } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { reportsApi } from '../../api/reportsHolidays';
import { teamsApi } from '../../api/org';

export default function ReportsRegion() {
  const { t } = useTranslation();
  const [month, setMonth] = useState(dayjs());
  const [teamId, setTeamId] = useState<string>();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const { data = [] } = useQuery({
    queryKey: ['report-summary', teamId, month.format('YYYY-MM')],
    queryFn: () => reportsApi.summary({ teamId, month: month.format('YYYY-MM') }),
  });

  return (
    <div>
      <Typography.Title level={3}>{t('reportsRegion.title')}</Typography.Title>
      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} />
          <Select style={{ width: 200 }} allowClear placeholder={t('reportsRegion.filterByTeam')} value={teamId} onChange={setTeamId} options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
          <a href={reportsApi.exportUrl({ teamId, month: month.format('YYYY-MM') })} target="_blank" rel="noreferrer">
            <Button icon={<DownloadOutlined />}>{t('reportsRegion.exportBtn')}</Button>
          </a>
        </div>
        <Table
          rowKey="userId"
          scroll={{ x: "max-content" }}
          dataSource={data}
          columns={[
            { title: t('reportsRegion.employeeNo'), dataIndex: 'employeeNo' },
            { title: t('reportsRegion.name'), dataIndex: 'name' },
            { title: t('reportsRegion.department'), dataIndex: 'department' },
            { title: t('reportsRegion.team'), dataIndex: 'team' },
            { title: t('reportsRegion.normalDays'), dataIndex: 'normalDays' },
            { title: t('reportsRegion.fullAttendanceDays'), dataIndex: 'fullAttendanceDays' },
            { title: t('reportsRegion.lateCount'), dataIndex: 'lateCount' },
            { title: t('reportsRegion.earlyLeaveCount'), dataIndex: 'earlyLeaveCount' },
            { title: t('reportsRegion.absentDays'), dataIndex: 'absentDays' },
            { title: t('reportsRegion.leaveDays'), dataIndex: 'leaveDays' },
            { title: t('reportsRegion.overtimeHours'), dataIndex: 'overtimeHours' },
            { title: t('reportsRegion.locationAnomalyCount'), dataIndex: 'locationAnomalyCount' },
            { title: t('reportsRegion.attendanceRate'), dataIndex: 'attendanceRate', render: (v) => `${v}%` },
          ]}
        />
      </Card>
    </div>
  );
}
