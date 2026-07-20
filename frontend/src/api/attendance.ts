import { apiClient } from './client';
import type { AttendanceRecord, AttendanceMode, OfficeAssignmentMode } from './types';

export interface TodayAttendance {
  record: AttendanceRecord | null;
  effectiveRule: {
    mode?: AttendanceMode;
    requiresClockIn: boolean;
    requiresClockOut: boolean;
    requiresPhoto: boolean;
    requiresBusinessMetric: boolean;
    businessMetricThreshold: number | null;
    officeAssignmentMode: OfficeAssignmentMode | 'NONE';
  };
}

export const attendanceApi = {
  clockIn: (data?: { lat?: number; lng?: number }) =>
    apiClient.post<AttendanceRecord>('/attendance/clock-in', data ?? {}).then((r) => r.data),
  clockOut: (data?: { lat?: number; lng?: number }) =>
    apiClient.post<AttendanceRecord>('/attendance/clock-out', data ?? {}).then((r) => r.data),
  today: () => apiClient.get<TodayAttendance>('/attendance/today').then((r) => r.data),
  myCalendar: (month?: string) => apiClient.get<AttendanceRecord[]>('/attendance/me', { params: { month } }).then((r) => r.data),
  list: (params?: { userId?: string; departmentId?: string; teamId?: string; month?: string }) =>
    apiClient.get<AttendanceRecord[]>('/attendance', { params }).then((r) => r.data),
};
