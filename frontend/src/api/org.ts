import { apiClient } from './client';
import type { Department, Office, Team, User, AttendanceMode, OfficeAttendanceRule } from './types';

export const departmentsApi = {
  tree: () => apiClient.get<Department[]>('/departments/tree').then((r) => r.data),
  list: () => apiClient.get<Department[]>('/departments').then((r) => r.data),
  create: (data: { name: string; parentId?: string; leaderId?: string }) =>
    apiClient.post<Department>('/departments', data).then((r) => r.data),
  update: (id: string, data: Partial<{ name: string; parentId: string; leaderId: string }>) =>
    apiClient.patch<Department>(`/departments/${id}`, data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/departments/${id}`).then((r) => r.data),
};

export const teamsApi = {
  list: () => apiClient.get<Team[]>('/teams').then((r) => r.data),
  get: (id: string) => apiClient.get<Team>(`/teams/${id}`).then((r) => r.data),
  create: (data: { name: string; departmentId: string; leaderId?: string }) =>
    apiClient.post<Team>('/teams', data).then((r) => r.data),
  update: (id: string, data: Partial<{ name: string; departmentId: string; leaderId: string }>) =>
    apiClient.patch<Team>(`/teams/${id}`, data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/teams/${id}`).then((r) => r.data),
  setModeConfig: (id: string, mode: AttendanceMode) =>
    apiClient.put(`/teams/${id}/mode-config`, { mode }).then((r) => r.data),
  getOfficeRule: (id: string) => apiClient.get<OfficeAttendanceRule | null>(`/teams/${id}/office-rule`).then((r) => r.data),
  setOfficeRule: (id: string, data: { startTime: string; endTime: string; lateGraceMinutes: number; earlyGraceMinutes: number }) =>
    apiClient.put(`/teams/${id}/office-rule`, data).then((r) => r.data),
};

export const officesApi = {
  list: () => apiClient.get<Office[]>('/offices').then((r) => r.data),
  create: (data: { name: string; address?: string; gpsLat?: number; gpsLng?: number }) =>
    apiClient.post<Office>('/offices', data).then((r) => r.data),
  update: (id: string, data: Partial<{ name: string; address: string; gpsLat: number; gpsLng: number; isActive: boolean }>) =>
    apiClient.patch<Office>(`/offices/${id}`, data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/offices/${id}`).then((r) => r.data),
};

export const usersApi = {
  list: (params?: { departmentId?: string; teamId?: string; keyword?: string }) =>
    apiClient.get<User[]>('/users', { params }).then((r) => r.data),
  me: () => apiClient.get<User>('/users/me').then((r) => r.data),
  get: (id: string) => apiClient.get<User>(`/users/${id}`).then((r) => r.data),
  create: (data: Record<string, unknown>) => apiClient.post<User>('/users', data).then((r) => r.data),
  update: (id: string, data: Record<string, unknown>) => apiClient.patch<User>(`/users/${id}`, data).then((r) => r.data),
  enable: (id: string) => apiClient.patch(`/users/${id}/enable`).then((r) => r.data),
  disable: (id: string) => apiClient.patch(`/users/${id}/disable`).then((r) => r.data),
  importExcel: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.post('/users/import', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data);
  },
};
