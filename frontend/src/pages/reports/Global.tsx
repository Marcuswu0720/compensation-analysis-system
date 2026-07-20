import { useState } from 'react';
import { Card, DatePicker, Table, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { reportsApi } from '../../api/reportsHolidays';

export default function ReportsGlobal() {
  const [month, setMonth] = useState(dayjs());
  const { data = [] } = useQuery({
    queryKey: ['report-global', month.format('YYYY-MM')],
    queryFn: () => reportsApi.global(month.format('YYYY-MM')),
  });

  return (
    <div>
      <Typography.Title level={3}>全局报表（总部只读）</Typography.Title>
      <Card>
        <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} style={{ marginBottom: 16 }} />
        <div style={{ width: '100%', height: 320, marginBottom: 24 }}>
          <ResponsiveContainer>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="department" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="lateCount" name="迟到次数" fill="#faad14" />
              <Bar dataKey="absentDays" name="缺勤天数" fill="#f5222d" />
              <Bar dataKey="leaveDays" name="请假天数" fill="#1677ff" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Table
          rowKey="department"
          dataSource={data}
          columns={[
            { title: '部门', dataIndex: 'department' },
            { title: '人数', dataIndex: 'users' },
            { title: '迟到次数', dataIndex: 'lateCount' },
            { title: '缺勤天数', dataIndex: 'absentDays' },
            { title: '请假天数', dataIndex: 'leaveDays' },
            { title: '加班时长', dataIndex: 'overtimeHours' },
          ]}
        />
      </Card>
    </div>
  );
}
