import { useState } from 'react';
import { Button, Card, DatePicker, Select, Table, Typography } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { reportsApi } from '../../api/reportsHolidays';
import { teamsApi } from '../../api/org';

export default function ReportsRegion() {
  const [month, setMonth] = useState(dayjs());
  const [teamId, setTeamId] = useState<string>();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const { data = [] } = useQuery({
    queryKey: ['report-summary', teamId, month.format('YYYY-MM')],
    queryFn: () => reportsApi.summary({ teamId, month: month.format('YYYY-MM') }),
  });

  return (
    <div>
      <Typography.Title level={3}>本地区报表</Typography.Title>
      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
          <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} />
          <Select style={{ width: 200 }} allowClear placeholder="按团队筛选" value={teamId} onChange={setTeamId} options={teams.map((t) => ({ value: t.id, label: t.name }))} />
          <a href={reportsApi.exportUrl({ teamId, month: month.format('YYYY-MM') })} target="_blank" rel="noreferrer">
            <Button icon={<DownloadOutlined />}>导出 Excel/CSV</Button>
          </a>
        </div>
        <Table
          rowKey="userId"
          dataSource={data}
          columns={[
            { title: '工号', dataIndex: 'employeeNo' },
            { title: '姓名', dataIndex: 'name' },
            { title: '部门', dataIndex: 'department' },
            { title: '团队', dataIndex: 'team' },
            { title: '正常出勤天数', dataIndex: 'normalDays' },
            { title: '全勤天数', dataIndex: 'fullAttendanceDays' },
            { title: '迟到次数', dataIndex: 'lateCount' },
            { title: '早退次数', dataIndex: 'earlyLeaveCount' },
            { title: '缺勤天数', dataIndex: 'absentDays' },
            { title: '请假天数', dataIndex: 'leaveDays' },
            { title: '加班时长', dataIndex: 'overtimeHours' },
            { title: '定位打卡异常次数', dataIndex: 'locationAnomalyCount' },
            { title: '出勤率', dataIndex: 'attendanceRate', render: (v) => `${v}%` },
          ]}
        />
      </Card>
    </div>
  );
}
