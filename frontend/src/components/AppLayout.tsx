import { useMemo } from 'react';
import { Layout, Menu, Avatar, Dropdown, Space, Tag, Select } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
} from '@ant-design/icons';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
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
];

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
