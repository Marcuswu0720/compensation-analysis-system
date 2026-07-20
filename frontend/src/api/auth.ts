import { apiClient } from './client';
import type { AuthUser } from './types';

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
}

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<LoginResponse>('/auth/login', { email, password }).then((r) => r.data),
  logout: (refreshToken: string) => apiClient.post('/auth/logout', { refreshToken }).then((r) => r.data),
};
