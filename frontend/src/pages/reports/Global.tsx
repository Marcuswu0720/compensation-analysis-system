import { useState } from 'react';
import { Card, DatePicker, Table, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { reportsApi } from '../../api/reportsHolidays';

export default function ReportsGlobal() {
  const { t } = useTranslation();
  const [month, setMonth] = useState(dayjs());
  const { data = [] } = useQuery({
    queryKey: ['report-global', month.format('YYYY-MM')],
    queryFn: () => reportsApi.global(month.format('YYYY-MM')),
  });

  return (
    <div>
      <Typography.Title level={3}>{t('reportsGlobal.title')}</Typography.Title>
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
              <Bar dataKey="lateCount" name={t('reportsGlobal.lateCount')} fill="#faad14" />
              <Bar dataKey="absentDays" name={t('reportsGlobal.absentDays')} fill="#f5222d" />
              <Bar dataKey="leaveDays" name={t('reportsGlobal.leaveDays')} fill="#1677ff" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Table
          rowKey="department"
          scroll={{ x: "max-content" }}
          dataSource={data}
          columns={[
            { title: t('reportsGlobal.department'), dataIndex: 'department' },
            { title: t('reportsGlobal.users'), dataIndex: 'users' },
            { title: t('reportsGlobal.lateCount'), dataIndex: 'lateCount' },
            { title: t('reportsGlobal.absentDays'), dataIndex: 'absentDays' },
            { title: t('reportsGlobal.leaveDays'), dataIndex: 'leaveDays' },
            { title: t('reportsGlobal.overtimeHours'), dataIndex: 'overtimeHours' },
          ]}
        />
      </Card>
    </div>
  );
}
