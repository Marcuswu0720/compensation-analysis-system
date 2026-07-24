import { Card, Col, Row, Statistic, Typography, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { useAuthStore } from '../store/authStore';
import { attendanceApi } from '../api/attendance';
import { STATUS_COLOR, useStatusLabel } from '../utils/status';

export default function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const isHq = user?.role === 'HQ';
  const isQc = user?.role === 'QC_TEAM';
  const noClockIn = isHq || isQc;
  const { t } = useTranslation();
  const statusLabel = useStatusLabel();

  const { data: today } = useQuery({
    queryKey: ['attendance-today'],
    queryFn: attendanceApi.today,
    enabled: !noClockIn,
  });

  return (
    <div>
      <Typography.Title level={3}>{t('dashboard.welcome', { name: user?.name })}</Typography.Title>
      <Row gutter={[16, 16]}>
        {!noClockIn && (
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic title={t('dashboard.todayDate')} value={dayjs().format('YYYY-MM-DD dddd')} />
              <div style={{ marginTop: 12 }}>
                {t('dashboard.todayStatus')}：
                {today?.record ? (
                  <Tag color={STATUS_COLOR[today.record.status]}>{statusLabel[today.record.status]}</Tag>
                ) : (
                  <Tag>{t('dashboard.noRecord')}</Tag>
                )}
              </div>
              <Link to="/clock-in">{t('dashboard.goClockIn')}</Link>
            </Card>
          </Col>
        )}
        <Col xs={24} sm={12} md={8}>
          <Card title={t('dashboard.quickLinks')}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {!noClockIn && <Link to="/my-attendance">{t('dashboard.myCalendar')}</Link>}
              {!noClockIn && <Link to="/leave/apply">{t('dashboard.applyLeave')}</Link>}
              {(user?.role === 'LOCAL_MANAGER' || user?.role === 'LOCAL_HR') && (
                <Link to="/reports/region">{t('dashboard.regionReport')}</Link>
              )}
              {(user?.role === 'HQ' || user?.role === 'LOCAL_HR') && <Link to="/reports/global">{t('dashboard.globalReport')}</Link>}
              {(isQc || user?.role === 'HQ' || user?.role === 'LOCAL_HR') && <Link to="/qc/anomalies">{t('dashboard.qcAnomalies')}</Link>}
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
