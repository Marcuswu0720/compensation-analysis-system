import type { AttendanceStatus, ApprovalStatus, VerifyStatus, AttendanceMode, SpecialEventType, Role } from '../api/types';

export const STATUS_LABEL: Record<AttendanceStatus, string> = {
  NORMAL: '正常',
  LATE: '迟到',
  EARLY_LEAVE: '早退',
  ABSENT: '缺勤',
  LEAVE: '请假',
  FULL_ATTENDANCE: '全勤',
  PENDING: '待核实/未打卡',
  UNCONFIGURED: '未配置考勤规则',
};

export const STATUS_COLOR: Record<AttendanceStatus, string> = {
  NORMAL: 'green',
  LATE: 'orange',
  EARLY_LEAVE: 'orange',
  ABSENT: 'red',
  LEAVE: 'blue',
  FULL_ATTENDANCE: 'purple',
  PENDING: 'default',
  UNCONFIGURED: 'magenta',
};

export const APPROVAL_LABEL: Record<ApprovalStatus, string> = {
  PENDING: '待审批',
  APPROVED: '已通过',
  REJECTED: '已驳回',
  CANCELLED: '已撤销',
};

export const APPROVAL_COLOR: Record<ApprovalStatus, string> = {
  PENDING: 'gold',
  APPROVED: 'green',
  REJECTED: 'red',
  CANCELLED: 'default',
};

export const VERIFY_LABEL: Record<VerifyStatus, string> = {
  PENDING: '待核实',
  APPROVED: '已通过',
  REJECTED: '已驳回',
};

export const VERIFY_COLOR: Record<VerifyStatus, string> = {
  PENDING: 'gold',
  APPROVED: 'green',
  REJECTED: 'red',
};

export const MODE_LABEL: Record<AttendanceMode, string> = {
  OFFICE: '办公室打卡',
  SHIFT: '排班打卡',
  LOCATION: '定位打卡',
};

export const EVENT_TYPE_LABEL: Record<SpecialEventType, string> = {
  EXTREME_WEATHER: '极端天气',
  EMERGENCY_EVENT: '突发事件',
};

export const ROLE_LABEL: Record<Role, string> = {
  EMPLOYEE: '员工',
  LOCAL_MANAGER: '本地小管理者',
  LOCAL_HR: '本地HR/HRIS',
  HQ: '总部（只读）',
};
