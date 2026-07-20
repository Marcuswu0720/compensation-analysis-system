import { apiClient } from './client';
import type { Holiday, ReportSummaryRow } from './types';

export const reportsApi = {
  summary: (params?: { userId?: string; departmentId?: string; teamId?: string; month?: string }) =>
    apiClient.get<ReportSummaryRow[]>('/reports/summary', { params }).then((r) => r.data),
  global: (month?: string) => apiClient.get('/reports/global', { params: { month } }).then((r) => r.data),
  exportUrl: (params: { departmentId?: string; teamId?: string; month?: string }) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return `${apiClient.defaults.baseURL}/reports/export?${qs}`;
  },
};

export const holidaysApi = {
  list: (year?: string) => apiClient.get<Holiday[]>('/holidays', { params: { year } }).then((r) => r.data),
  create: (data: { date: string; name: string; isWorkday?: boolean }) =>
    apiClient.post<Holiday>('/holidays', data).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/holidays/${id}`).then((r) => r.data),
};
