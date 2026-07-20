import { apiClient } from './client';
import type { SpecialEvent, SpecialEventType } from './types';

export const specialEventsApi = {
  list: () => apiClient.get<SpecialEvent[]>('/special-events').then((r) => r.data),
  create: (data: { type: SpecialEventType; affectedOfficeIds: string[]; startTime: string; endTime: string; remark?: string }) =>
    apiClient.post<SpecialEvent>('/special-events', data).then((r) => r.data),
  revoke: (id: string) => apiClient.patch<SpecialEvent>(`/special-events/${id}/revoke`).then((r) => r.data),
};
