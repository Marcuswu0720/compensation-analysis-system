import { apiClient } from './client';
import type { Notification } from './types';

export const notificationsApi = {
  list: (unreadOnly?: boolean) =>
    apiClient.get<Notification[]>('/notifications', { params: unreadOnly ? { unreadOnly: 'true' } : undefined }).then((r) => r.data),
  unreadCount: () => apiClient.get<number>('/notifications/unread-count').then((r) => r.data),
  markRead: (id: string) => apiClient.patch(`/notifications/${id}/read`).then((r) => r.data),
  markAllRead: () => apiClient.patch('/notifications/read-all').then((r) => r.data),
};
