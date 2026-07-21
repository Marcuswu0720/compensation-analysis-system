import { Card, Col, Row, Statistic, Typography, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import dayjs from 'dayjs';
import { useAuthStore } from '../store/authStore';
import { attendanceApi } from '../api/attendance';
import { STATUS_LABEL, STATUS_COLOR } from '../utils/status';

export default function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const isHq = user?.role === 'HQ';

  const { data: today } = useQuery({
    queryKey: ['attendance-today'],
    queryFn: attendanceApi.today,
    enabled: !isHq,
  });

  return (
    <div>
      <Typography.Title level={3}>欢迎，{user?.name}</Typography.Title>
      <Row gutter={[16, 16]}>
        {!isHq && (
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic title="今日日期" value={dayjs().format('YYYY-MM-DD dddd')} />
              <div style={{ marginTop: 12 }}>
                今日状态：
                {today?.record ? (
                  <Tag color={STATUS_COLOR[today.record.status]}>{STATUS_LABEL[today.record.status]}</Tag>
                ) : (
                  <Tag>未打卡</Tag>
                )}
              </div>
              <Link to="/clock-in">去打卡 →</Link>
            </Card>
          </Col>
        )}
        <Col xs={24} sm={12} md={8}>
          <Card title="快捷入口">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {!isHq && <Link to="/my-attendance">查看我的考勤日历</Link>}
              {!isHq && <Link to="/leave/apply">提交请假/加班申请</Link>}
              {(user?.role === 'LOCAL_MANAGER' || user?.role === 'LOCAL_HR') && (
                <Link to="/reports/region">查看本地区报表</Link>
              )}
              {(user?.role === 'HQ' || user?.role === 'LOCAL_HR') && <Link to="/reports/global">查看全局报表</Link>}
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
