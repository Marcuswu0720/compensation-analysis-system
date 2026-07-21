import { apiClient } from './client';
import type { ApprovalStatus, LeaveApplication, LeaveType, OvertimeApplication } from './types';

export const leaveApi = {
  types: (activeOnly = false) => apiClient.get<LeaveType[]>('/leave/types', { params: { activeOnly } }).then((r) => r.data),
  createType: (data: { code: string; name: string }) => apiClient.post<LeaveType>('/leave/types', data).then((r) => r.data),
  setTypeActive: (id: string, isActive: boolean) => apiClient.patch(`/leave/types/${id}/active`, { isActive }).then((r) => r.data),
  apply: (data: { typeId: string; startTime: string; endTime: string; reason: string }) =>
    apiClient.post<LeaveApplication>('/leave/applications', data).then((r) => r.data),
  mine: () => apiClient.get<LeaveApplication[]>('/leave/applications/me').then((r) => r.data),
  list: (params?: { status?: ApprovalStatus; departmentId?: string; teamId?: string }) =>
    apiClient.get<LeaveApplication[]>('/leave/applications', { params }).then((r) => r.data),
  cancel: (id: string) => apiClient.patch(`/leave/applications/${id}/cancel`).then((r) => r.data),
  approve: (id: string, comment?: string) => apiClient.patch(`/leave/applications/${id}/approve`, { comment }).then((r) => r.data),
  reject: (id: string, comment?: string) => apiClient.patch(`/leave/applications/${id}/reject`, { comment }).then((r) => r.data),
  // 本地HR/HRIS 本人提交的申请没有上级审批，改由总部特批（问题反馈 2.6）
  specialPending: () => apiClient.get<LeaveApplication[]>('/leave/applications/special-pending').then((r) => r.data),
  specialApprove: (id: string, comment?: string) => apiClient.patch(`/leave/applications/${id}/special-approve`, { comment }).then((r) => r.data),
  specialReject: (id: string, comment?: string) => apiClient.patch(`/leave/applications/${id}/special-reject`, { comment }).then((r) => r.data),
};

export const overtimeApi = {
  apply: (data: { date: string; hours: number; reason: string }) =>
    apiClient.post<OvertimeApplication>('/overtime/applications', data).then((r) => r.data),
  mine: () => apiClient.get<OvertimeApplication[]>('/overtime/applications/me').then((r) => r.data),
  list: (params?: { status?: ApprovalStatus; departmentId?: string; teamId?: string }) =>
    apiClient.get<OvertimeApplication[]>('/overtime/applications', { params }).then((r) => r.data),
  cancel: (id: string) => apiClient.patch(`/overtime/applications/${id}/cancel`).then((r) => r.data),
  approve: (id: string, comment?: string) => apiClient.patch(`/overtime/applications/${id}/approve`, { comment }).then((r) => r.data),
  reject: (id: string, comment?: string) => apiClient.patch(`/overtime/applications/${id}/reject`, { comment }).then((r) => r.data),
  specialPending: () => apiClient.get<OvertimeApplication[]>('/overtime/applications/special-pending').then((r) => r.data),
  specialApprove: (id: string, comment?: string) => apiClient.patch(`/overtime/applications/${id}/special-approve`, { comment }).then((r) => r.data),
  specialReject: (id: string, comment?: string) => apiClient.patch(`/overtime/applications/${id}/special-reject`, { comment }).then((r) => r.data),
};
