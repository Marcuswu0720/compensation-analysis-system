import { apiClient } from './client';
import type { LocationAnomaly, AnomalyReviewStatus } from './types';

export const locationAnomaliesApi = {
  list: (status?: AnomalyReviewStatus) =>
    apiClient.get<LocationAnomaly[]>('/location-anomalies', { params: { status } }).then((r) => r.data),
  review: (id: string, reviewNote?: string) =>
    apiClient.patch<LocationAnomaly>(`/location-anomalies/${id}/review`, { reviewNote }).then((r) => r.data),
};
