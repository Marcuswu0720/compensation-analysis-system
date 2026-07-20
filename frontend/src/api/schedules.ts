import { apiClient } from './client';
import type { Shift, ScheduleAssignment } from './types';

export const schedulesApi = {
  listShifts: (teamId?: string) => apiClient.get<Shift[]>('/schedules/shifts', { params: { teamId } }).then((r) => r.data),
  createShift: (data: { teamId: string; name: string; startTime: string; endTime: string }) =>
    apiClient.post<Shift>('/schedules/shifts', data).then((r) => r.data),
  updateShift: (id: string, data: Partial<{ name: string; startTime: string; endTime: string }>) =>
    apiClient.patch<Shift>(`/schedules/shifts/${id}`, data).then((r) => r.data),
  removeShift: (id: string) => apiClient.delete(`/schedules/shifts/${id}`).then((r) => r.data),
  batchGenerate: (data: { userIds: string[]; shiftId: string; dateFrom: string; dateTo: string; daysOfWeek?: number[] }) =>
    apiClient.post('/schedules/assignments/batch-generate', data).then((r) => r.data),
  changeAssignment: (id: string, newShiftId: string) =>
    apiClient.patch(`/schedules/assignments/${id}/change`, { newShiftId }).then((r) => r.data),
  addTemporary: (data: { userId: string; shiftId: string; date: string }) =>
    apiClient.post('/schedules/assignments/temporary', data).then((r) => r.data),
  listAssignments: (params?: { userId?: string; teamId?: string; from?: string; to?: string }) =>
    apiClient.get<ScheduleAssignment[]>('/schedules/assignments', { params }).then((r) => r.data),
  history: (userId: string, date: string) =>
    apiClient.get<ScheduleAssignment[]>('/schedules/assignments/history', { params: { userId, date } }).then((r) => r.data),
};
