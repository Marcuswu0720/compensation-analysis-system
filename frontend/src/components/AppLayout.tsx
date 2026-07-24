import { useMemo } from 'react';
import { Layout, Menu, Avatar, Dropdown, Space, Tag, Select, Badge, Popover, List, Button, Empty, Typography } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import {
  DashboardOutlined,
  ClockCircleOutlined,
  CalendarOutlined,
  FileTextOutlined,
  AuditOutlined,
  EnvironmentOutlined,
  ScheduleOutlined,
  WarningOutlined,
  BarChartOutlined,
  GlobalOutlined,
  ApartmentOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  BellOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
import { notificationsApi } from '../api/notifications';
import { useRoleLabel } from '../utils/status';
import { setLanguage } from '../i18n';
import type { Role } from '../api/types';

const { Header, Sider, Content } = Layout;

interface MenuDef {
  key: string;
  labelKey: string;
  icon: React.ReactNode;
  roles: Role[];
}

const MENU_ITEMS: MenuDef[] = [
  { key: '/dashboard', labelKey: 'menu.dashboard', icon: <DashboardOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR', 'HQ'] },
  { key: '/clock-in', labelKey: 'menu.clockIn', icon: <ClockCircleOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/my-attendance', labelKey: 'menu.myAttendance', icon: <CalendarOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/leave/apply', labelKey: 'menu.leaveApply', icon: <FileTextOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/leave/my-applications', labelKey: 'menu.myApplications', icon: <FileTextOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/approval', labelKey: 'menu.approval', icon: <AuditOutlined />, roles: ['LOCAL_HR'] },
  { key: '/special-approval', labelKey: 'menu.specialApproval', icon: <AuditOutlined />, roles: ['HQ'] },
  { key: '/location-checkin/review', labelKey: 'menu.locationCheckinReview', icon: <EnvironmentOutlined />, roles: ['LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/schedule', labelKey: 'menu.schedule', icon: <ScheduleOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/special-events', labelKey: 'menu.specialEvents', icon: <WarningOutlined />, roles: ['LOCAL_HR'] },
  { key: '/reports/region', labelKey: 'menu.reportsRegion', icon: <BarChartOutlined />, roles: ['LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/reports/global', labelKey: 'menu.reportsGlobal', icon: <GlobalOutlined />, roles: ['HQ', 'LOCAL_HR'] },
  { key: '/admin/employees', labelKey: 'menu.adminEmployees', icon: <UserOutlined />, roles: ['LOCAL_HR'] },
  { key: '/admin/teams', labelKey: 'menu.adminTeams', icon: <ApartmentOutlined />, roles: ['LOCAL_HR'] },
  { key: '/admin/rules', labelKey: 'menu.adminRules', icon: <SettingOutlined />, roles: ['LOCAL_HR'] },
  { key: '/qc/anomalies', labelKey: 'menu.qcAnomalies', icon: <WarningOutlined />, roles: ['QC_TEAM', 'HQ', 'LOCAL_HR'] },
];

function renderNotificationText(t: (key: string, opts?: Record<string, unknown>) => string, n: { type: string; title: string; message: string; params: Record<string, string | number> | null }) {
  // 已知类型走 i18n + params 按当前语言渲染；未知类型（如未来新增但前端未升级）兜底展示服务端存的原始文案
  if (n.type === 'LOCATION_ANOMALY' && n.params) {
    return { title: t('notifications.types.LOCATION_ANOMALY.title'), message: t('notifications.types.LOCATION_ANOMALY.message', n.params) };
  }
  return { title: n.title, message: n.message };
}

function NotificationBell() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: unreadCount = 0 } = useQuery({
    queryKey: ['notifications-unread-count'],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 30000,
  });
  const { data: notifications = [] } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => notificationsApi.list(),
  });

  const handleOpenChange = (open: boolean) => {
    if (open) queryClient.invalidateQueries({ queryKey: ['notifications'] });
  };

  const handleClickItem = async (id: string, relatedEntityType: string | null) => {
    await notificationsApi.markRead(id);
    queryClient.invalidateQueries({ queryKey: ['notifications'] });
    queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] });
    if (relatedEntityType === 'LOCATION_CHECKIN_PHOTO') navigate('/qc/anomalies');
  };

  const markAllRead = async () => {
    await notificationsApi.markAllRead();
    queryClient.invalidateQueries({ queryKey: ['notifications'] });
    queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] });
  };

  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      onOpenChange={handleOpenChange}
      title={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <span>{t('notifications.title')}</span>
          {unreadCount > 0 && (
            <Button type="link" size="small" onClick={markAllRead}>
              {t('notifications.markAllRead')}
            </Button>
          )}
        </Space>
      }
      content={
        <div style={{ width: 320, maxHeight: 360, overflowY: 'auto' }}>
          {notifications.length === 0 ? (
            <Empty description={t('notifications.empty')} />
          ) : (
            <List
              size="small"
              dataSource={notifications}
              renderItem={(n) => {
                const text = renderNotificationText(t, n);
                return (
                  <List.Item
                    style={{ cursor: 'pointer', background: n.isRead ? undefined : '#f0f5ff', padding: 8 }}
                    onClick={() => handleClickItem(n.id, n.relatedEntityType)}
                  >
                    <div style={{ width: '100%' }}>
                      <Typography.Text strong={!n.isRead}>{text.title}</Typography.Text>
                      <div style={{ fontSize: 12, color: '#888' }}>{text.message}</div>
                      <div style={{ fontSize: 12, color: '#bbb' }}>{dayjs(n.createdAt).format('YYYY-MM-DD HH:mm')}</div>
                    </div>
                  </List.Item>
                );
              }}
            />
          )}
        </div>
      }
    >
      <Badge count={unreadCount} size="small">
        <BellOutlined style={{ fontSize: 18, cursor: 'pointer' }} />
      </Badge>
    </Popover>
  );
}

export function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const roleLabel = useRoleLabel();

  const items = useMemo(
    () => MENU_ITEMS.filter((m) => user && m.roles.includes(user.role)).map((m) => ({ key: m.key, icon: m.icon, label: t(m.labelKey) })),
    [user, t],
  );

  const handleLogout = async () => {
    try {
      if (refreshToken) await authApi.logout(refreshToken);
    } catch {
      // ignore network errors on logout
    }
    logout();
    navigate('/login');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0" width={220}>
        <div style={{ color: '#fff', padding: 16, fontSize: 16, fontWeight: 600 }}>{t('common.appTitle')}</div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={(e) => navigate(e.key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '8px 16px',
            height: 'auto',
            lineHeight: 'normal',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'flex-end',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <Select
            value={i18n.language === 'zh' ? 'zh' : 'en'}
            onChange={(v: 'en' | 'zh') => setLanguage(v)}
            size="small"
            style={{ width: 110 }}
            options={[
              { value: 'en', label: 'English' },
              { value: 'zh', label: '简体中文' },
            ]}
          />
          <NotificationBell />
          <Dropdown
            menu={{
              items: [{ key: 'logout', icon: <LogoutOutlined />, label: t('common.logout'), onClick: handleLogout }],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.name}</span>
              <Tag color="blue">{user ? roleLabel[user.role] : ''}</Tag>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
