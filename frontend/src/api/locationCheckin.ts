import { apiClient } from './client';
import type { LocationCheckInPhoto, VerifyStatus } from './types';

export const locationCheckinApi = {
  upload: (data: { photo: File; lat: number; lng: number; takenAt?: string; businessMetricValue?: number }) => {
    const form = new FormData();
    form.append('photo', data.photo);
    form.append('lat', String(data.lat));
    form.append('lng', String(data.lng));
    if (data.takenAt) form.append('takenAt', data.takenAt);
    if (data.businessMetricValue !== undefined) form.append('businessMetricValue', String(data.businessMetricValue));
    return apiClient.post<LocationCheckInPhoto>('/location-checkin', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data);
  },
  pending: () => apiClient.get<LocationCheckInPhoto[]>('/location-checkin/pending').then((r) => r.data),
  trajectory: (userId: string, date: string) =>
    apiClient.get<LocationCheckInPhoto[]>('/location-checkin/trajectory', { params: { userId, date } }).then((r) => r.data),
  list: (params?: { userId?: string; teamId?: string; from?: string; to?: string; verifyStatus?: VerifyStatus }) =>
    apiClient.get<LocationCheckInPhoto[]>('/location-checkin', { params }).then((r) => r.data),
  verify: (id: string, status: VerifyStatus, remark?: string) =>
    apiClient.patch(`/location-checkin/${id}/verify`, { status, remark }).then((r) => r.data),
};
