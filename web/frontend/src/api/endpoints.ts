/**
 * API endpoint functions and types.
 */

import { apiClient } from './client';

// Types
export interface UserProfile {
  user_id: string;
  username: string;
  discriminator: string;
  avatar: string | null;
  is_admin: boolean;
  is_moderator: boolean;
}

export interface StatsOverview {
  total_verified: number;
  by_status: {
    main: number;
    affiliate: number;
    non_member: number;
    unknown: number;
  };
  voice_active_count: number;
}

export interface VerificationRecord {
  user_id: number;
  rsi_handle: string;
  membership_status: string | null;
  community_moniker: string | null;
  last_updated: number;
  needs_reverify: boolean;
}

export interface VoiceChannelRecord {
  id: number;
  guild_id: number;
  jtc_channel_id: number;
  owner_id: number;
  voice_channel_id: number;
  created_at: number;
  last_activity: number;
  is_active: boolean;
}

export interface VoiceChannelMember {
  user_id: number;
  username: string | null;
  display_name: string | null;
  rsi_handle: string | null;
  membership_status: string | null;
  is_owner: boolean;
}

export interface ActiveVoiceChannel {
  voice_channel_id: number;
  guild_id: number;
  jtc_channel_id: number;
  owner_id: number;
  owner_username: string | null;
  owner_rsi_handle: string | null;
  owner_membership_status: string | null;
  created_at: number;
  last_activity: number;
  channel_name: string | null;
  members: VoiceChannelMember[];
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
}

export interface HealthOverview {
  status: string;
  uptime_seconds: number;
  db_ok: boolean;
  discord_latency_ms: number | null;
  system: SystemMetrics;
}

export interface StructuredError {
  time: string;
  error_type: string;
  component: string;
  message?: string | null;
  traceback?: string | null;
}

// API functions
export const authApi = {
  getMe: async () => {
    const response = await apiClient.get<{ success: boolean; user: UserProfile | null }>('/api/auth/me');
    return response.data;
  },
  logout: async () => {
    const response = await apiClient.post('/auth/logout');
    return response.data;
  },
};

export const statsApi = {
  getOverview: async () => {
    const response = await apiClient.get<{ success: boolean; data: StatsOverview }>('/api/stats/overview');
    return response.data;
  },
};

export const usersApi = {
  search: async (query: string, page = 1, pageSize = 20) => {
    const response = await apiClient.get<{
      success: boolean;
      items: VerificationRecord[];
      total: number;
      page: number;
      page_size: number;
    }>('/api/users/search', {
      params: { query, page, page_size: pageSize },
    });
    return response.data;
  },
};

export const voiceApi = {
  getActive: async () => {
    const response = await apiClient.get<{
      success: boolean;
      items: ActiveVoiceChannel[];
      total: number;
    }>('/api/voice/active');
    return response.data;
  },
  search: async (userId: number) => {
    const response = await apiClient.get<{
      success: boolean;
      items: VoiceChannelRecord[];
      total: number;
    }>('/api/voice/search', {
      params: { user_id: userId },
    });
    return response.data;
  },
};

export const healthApi = {
  getOverview: async () => {
    const response = await apiClient.get<{ success: boolean; data: HealthOverview }>('/api/health/overview');
    return response.data;
  },
};

export const errorsApi = {
  getLast: async (limit: number = 1) => {
    const response = await apiClient.get<{ success: boolean; errors: StructuredError[] }>(
      '/api/errors/last',
      { params: { limit } }
    );
    return response.data;
  },
};

export const logsApi = {
  exportLogs: async (maxBytes: number = 1048576) => {
    const response = await apiClient.get('/api/logs/export', {
      params: { max_bytes: maxBytes },
      responseType: 'blob',
    });
    
    // Trigger download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'bot.log.tail.txt');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
