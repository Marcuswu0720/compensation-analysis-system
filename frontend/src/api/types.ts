export type Role = 'EMPLOYEE' | 'LOCAL_MANAGER' | 'LOCAL_HR' | 'HQ' | 'QC_TEAM';

export type AttendanceMode = 'OFFICE' | 'SHIFT' | 'LOCATION' | 'HOME_OFFICE';

export type AttendanceStatus =
  | 'NORMAL'
  | 'LATE'
  | 'EARLY_LEAVE'
  | 'ABSENT'
  | 'LEAVE'
  | 'FULL_ATTENDANCE'
  | 'PENDING'
  | 'UNCONFIGURED';

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

export type VerifyStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export type SpecialEventType = 'EXTREME_WEATHER' | 'EMERGENCY_EVENT';

export type OfficeAssignmentMode = 'NEAREST_AUTO' | 'FIXED' | 'NONE';

export interface AuthUser {
  id: string;
  employeeNo: string;
  name: string;
  email: string;
  role: Role;
  departmentId: string | null;
  teamId: string | null;
}

export interface Department {
  id: string;
  name: string;
  parentId: string | null;
  leaderId: string | null;
  children?: Department[];
}

export interface Team {
  id: string;
  name: string;
  departmentId: string;
  leaderId: string | null;
  leader?: { id: string; name: string } | null;
  department?: Department;
  modeConfig?: { mode: AttendanceMode } | null;
}

export interface Office {
  id: string;
  name: string;
  address: string | null;
  gpsLat: number | null;
  gpsLng: number | null;
  allowedRadiusMeters: number;
  isActive: boolean;
}

export interface User {
  id: string;
  employeeNo: string;
  name: string;
  email: string;
  role: Role;
  departmentId: string | null;
  teamId: string | null;
  managerId: string | null;
  position: string | null;
  officeId: string | null;
  hireDate: string | null;
  isActive: boolean;
  department?: Department;
  team?: Team;
}

export interface AttendanceRecord {
  id: string;
  userId: string;
  date: string;
  clockInAt: string | null;
  clockOutAt: string | null;
  status: AttendanceStatus;
  source: string;
  lateMinutes: number;
  earlyMinutes: number;
  clockInLat: number | null;
  clockInLng: number | null;
  matchedOffice?: { id: string; name: string } | null;
  remark: string | null;
  user?: { id: string; name: string; employeeNo: string };
}

export interface SpecialEvent {
  id: string;
  type: SpecialEventType;
  startTime: string;
  endTime: string;
  createdById: string;
  createdAt: string;
  revokedById: string | null;
  revokedAt: string | null;
  remark: string | null;
  affectedOffices: { office: Office }[];
}

export interface Shift {
  id: string;
  teamId: string;
  name: string;
  nameEn: string | null;
  startTime: string;
  endTime: string;
}

export interface ScheduleAssignment {
  id: string;
  userId: string;
  shiftId: string;
  date: string;
  isTemporary: boolean;
  shift: Shift;
  user: { id: string; name: string; employeeNo: string };
}

export interface LocationCheckInPhoto {
  id: string;
  userId: string;
  photoUrl: string;
  gpsLat: number;
  gpsLng: number;
  takenAt: string;
  verifiedById: string | null;
  verifiedAt: string | null;
  verifyStatus: VerifyStatus;
  businessMetricValue: number | null;
  isWithinRange: boolean | null;
  user?: { id: string; name: string; employeeNo: string; team?: Team };
}

export interface LeaveType {
  id: string;
  code: string;
  name: string;
  nameEn: string | null;
  isActive: boolean;
}

export interface LeaveApplication {
  id: string;
  userId: string;
  typeId: string;
  startTime: string;
  endTime: string;
  reason: string;
  status: ApprovalStatus;
  approverId: string | null;
  approveComment: string | null;
  createdAt: string;
  type?: LeaveType;
  user?: { id: string; name: string; employeeNo: string };
}

export interface OvertimeApplication {
  id: string;
  userId: string;
  date: string;
  hours: number;
  reason: string;
  status: ApprovalStatus;
  approverId: string | null;
  approveComment: string | null;
  createdAt: string;
  user?: { id: string; name: string; employeeNo: string };
}

export interface RuleTemplate {
  id: string;
  teamId: string;
  requiresClockIn: boolean;
  requiresClockOut: boolean;
  requiresPhoto: boolean;
  photoIntervalThresholdMinutes: number | null;
  photoIntervalPreWarnMinutes: number | null;
  requiresBusinessMetric: boolean;
  businessMetricThreshold: number | null;
  businessMetricSource: string | null;
  officeAssignmentMode: OfficeAssignmentMode;
  offices: Office[];
}

export interface OfficeAttendanceRule {
  id: string;
  teamId: string;
  startTime: string;
  endTime: string;
  lateGraceMinutes: number;
  earlyGraceMinutes: number;
  offices: Office[];
}

export interface ReportSummaryRow {
  userId: string;
  name: string;
  employeeNo: string;
  department?: string;
  team?: string;
  normalDays: number;
  fullAttendanceDays: number;
  lateCount: number;
  earlyLeaveCount: number;
  absentDays: number;
  leaveDays: number;
  overtimeHours: number;
  locationAnomalyCount: number;
  attendanceRate: number;
}

export interface Holiday {
  id: string;
  date: string;
  name: string;
  isWorkday: boolean;
}

export type AnomalyReviewStatus = 'PENDING' | 'REVIEWED';

export interface LocationAnomaly {
  id: string;
  photoId: string;
  userId: string;
  intervalMinutes: number;
  thresholdMinutes: number;
  status: AnomalyReviewStatus;
  reviewNote: string | null;
  reviewedById: string | null;
  reviewedAt: string | null;
  createdAt: string;
  user: { id: string; name: string; employeeNo: string; team?: Team };
  photo: { id: string; photoUrl: string; takenAt: string; gpsLat: number; gpsLng: number };
}

export interface Notification {
  id: string;
  userId: string;
  type: string;
  title: string;
  message: string;
  params: Record<string, string | number> | null;
  relatedEntityType: string | null;
  relatedEntityId: string | null;
  isRead: boolean;
  createdAt: string;
}
