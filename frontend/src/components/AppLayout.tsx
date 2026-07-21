import { useMemo } from 'react';
import { Layout, Menu, Avatar, Dropdown, Space, Tag } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
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
import type { Role } from '../api/types';

const { Header, Sider, Content } = Layout;

const ROLE_LABEL: Record<Role, string> = {
  EMPLOYEE: '员工',
  LOCAL_MANAGER: '本地小管理者',
  LOCAL_HR: '本地HR/HRIS',
  HQ: '总部（只读）',
};

interface MenuDef {
  key: string;
  label: string;
  icon: React.ReactNode;
  roles: Role[];
}

const MENU_ITEMS: MenuDef[] = [
  { key: '/dashboard', label: '首页', icon: <DashboardOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR', 'HQ'] },
  { key: '/clock-in', label: '打卡', icon: <ClockCircleOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/my-attendance', label: '个人考勤日历', icon: <CalendarOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/leave/apply', label: '请假/加班申请', icon: <FileTextOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/leave/my-applications', label: '我的申请记录', icon: <FileTextOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/approval', label: '待审批列表', icon: <AuditOutlined />, roles: ['LOCAL_HR'] },
  { key: '/special-approval', label: '总部特批', icon: <AuditOutlined />, roles: ['HQ'] },
  { key: '/location-checkin/review', label: '定位打卡核实', icon: <EnvironmentOutlined />, roles: ['LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/schedule', label: '排班表', icon: <ScheduleOutlined />, roles: ['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/special-events', label: '特殊事件标记', icon: <WarningOutlined />, roles: ['LOCAL_HR'] },
  { key: '/reports/region', label: '本地区报表', icon: <BarChartOutlined />, roles: ['LOCAL_MANAGER', 'LOCAL_HR'] },
  { key: '/reports/global', label: '全局报表', icon: <GlobalOutlined />, roles: ['HQ', 'LOCAL_HR'] },
  { key: '/admin/employees', label: '员工管理', icon: <UserOutlined />, roles: ['LOCAL_HR'] },
  { key: '/admin/teams', label: '部门/团队管理', icon: <ApartmentOutlined />, roles: ['LOCAL_HR'] },
  { key: '/admin/rules', label: '考勤规则配置', icon: <SettingOutlined />, roles: ['LOCAL_HR'] },
];

export function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const location = useLocation();

  const items = useMemo(
    () => MENU_ITEMS.filter((m) => user && m.roles.includes(user.role)).map((m) => ({ key: m.key, icon: m.icon, label: m.label })),
    [user],
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
        <div style={{ color: '#fff', padding: 16, fontSize: 16, fontWeight: 600 }}>考勤管理系统</div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={(e) => navigate(e.key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 16px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Dropdown
            menu={{
              items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout }],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.name}</span>
              <Tag color="blue">{user ? ROLE_LABEL[user.role] : ''}</Tag>
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
