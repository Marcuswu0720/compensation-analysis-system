import { apiClient } from './client';
import type { RuleTemplate } from './types';

export const ruleTemplatesApi = {
  list: () => apiClient.get<RuleTemplate[]>('/rule-templates').then((r) => r.data),
  get: (teamId: string) => apiClient.get<RuleTemplate | null>(`/rule-templates/${teamId}`).then((r) => r.data),
  upsert: (teamId: string, data: Omit<RuleTemplate, 'id' | 'teamId'>) =>
    apiClient.put<RuleTemplate>(`/rule-templates/${teamId}`, data).then((r) => r.data),
  remove: (teamId: string) => apiClient.delete(`/rule-templates/${teamId}`).then((r) => r.data),
  evaluateBusinessMetric: (userId: string, date: string) =>
    apiClient.post('/rule-templates/evaluate-business-metric', { userId, date }).then((r) => r.data),
};
