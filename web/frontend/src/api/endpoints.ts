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
  active_guild_id?: string | null;
}

export interface GuildSummary {
  guild_id: string;
  guild_name: string;
  icon_url: string | null;
}

export interface GuildRole {
  id: number;
  name: string;
  color: number | null;
}

export interface GuildInfo {
  guild_id: string;
  guild_name: string;
  icon_url: string | null;
}

export interface DiscordChannel {
  id: string;  // Changed from number to string to preserve Discord snowflake precision
  name: string;
  category: string | null;
  position: number;
}

export interface BotRoleSettingsPayload {
  bot_admins: number[];
  lead_moderators: number[];
  main_role: number[];
  affiliate_role: number[];
  nonmember_role: number[];
}

export interface BotChannelSettingsPayload {
  verification_channel_id: string | null;  // Changed to string to preserve precision
  bot_spam_channel_id: string | null;
  public_announcement_channel_id: string | null;
  leadership_announcement_channel_id: string | null;
}

export interface VoiceSelectableRolesPayload {
  selectable_roles: number[];
}

export interface OrganizationSettingsPayload {
  organization_sid: string | null;
  organization_name: string | null;
}

export interface OrganizationValidationRequest {
  sid: string;
}

export interface OrganizationValidationResponse {
  success: boolean;
  is_valid: boolean;
  sid: string;
  name: string | null;
  error: string | null;
}

export interface ReadOnlyYamlConfig {
  rsi?: Record<string, any> | null;
  voice?: Record<string, any> | null;
  voice_debug_logging_enabled?: boolean | null;
}

export interface GuildConfigData {
  roles: BotRoleSettingsPayload;
  channels: BotChannelSettingsPayload;
  voice: VoiceSelectableRolesPayload;
  organization: OrganizationSettingsPayload;
  read_only?: ReadOnlyYamlConfig | null;
}

export interface GuildConfigUpdateRequest {
  roles?: BotRoleSettingsPayload;
  channels?: BotChannelSettingsPayload;
  voice?: VoiceSelectableRolesPayload;
  organization?: OrganizationSettingsPayload;
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
  main_orgs: string[] | null;
  affiliate_orgs: string[] | null;
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

export interface EnrichedUser {
  discord_id: string;
  username: string;
  discriminator: string;
  global_name: string | null;
  avatar_url: string | null;
  membership_status: string | null;
  rsi_handle: string | null;
  community_moniker: string | null;
  joined_at: string | null;
  created_at: string | null;
  last_updated: number | null;
  needs_reverify: boolean;
  roles: Array<{ id: number; name: string; color: number | null }>;
  main_orgs: string[] | null;
  affiliate_orgs: string[] | null;
}

export interface UsersListResponse {
  success: boolean;
  items: EnrichedUser[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ExportUsersRequest {
  membership_status?: string | null;
  membership_statuses?: string[] | null;
  role_ids?: number[] | null;
  selected_ids?: string[] | null;
  exclude_ids?: string[] | null;
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
  getGuilds: async () => {
    const response = await apiClient.get<{ success: boolean; guilds: GuildSummary[] }>(
      '/api/auth/guilds'
    );
    return response.data;
  },
  selectGuild: async (guildId: string) => {
    const response = await apiClient.post<{ success: boolean }>(
      '/api/auth/select-guild',
      { guild_id: guildId }
    );
    return response.data;
  },
  getBotInviteUrl: async () => {
    const response = await apiClient.get<{ invite_url: string }>(
      '/api/auth/bot-invite-url'
    );
    return response.data;
  },
  clearActiveGuild: async () => {
    const response = await apiClient.delete<{ success: boolean }>(
      '/api/auth/active-guild'
    );
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

  getUsers: async (
    page: number = 1,
    pageSize: number = 25,
    membershipStatuses?: string[] | null
  ): Promise<UsersListResponse> => {
    const params: Record<string, any> = {
      page,
      page_size: pageSize,
    };
    
    if (membershipStatuses && membershipStatuses.length > 0) {
      const filtered = membershipStatuses.filter(s => s && s !== 'all');
      if (filtered.length > 0) {
        if (filtered.length === 1) {
          params.membership_status = filtered[0];
        }
        params.membership_statuses = filtered.join(',');
      }
    }
    
    const response = await apiClient.get<UsersListResponse>('/api/users', { params });
    return response.data;
  },

  exportUsers: async (filters: ExportUsersRequest): Promise<void> => {
    const response = await apiClient.post('/api/users/export', filters, {
      responseType: 'blob',
    });
    
    // Extract filename from Content-Disposition header
    const contentDisposition = response.headers['content-disposition'];
    let filename = 'members_export.csv';
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
      if (filenameMatch) {
        filename = filenameMatch[1];
      }
    }
    
    // Trigger download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
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

export const guildApi = {
  getGuildInfo: async (guildId: string) => {
    const response = await apiClient.get<{ success: boolean; guild: GuildInfo }>(
      `/api/guilds/${guildId}/info`
    );
    return response.data;
  },
  getGuildConfig: async (guildId: string) => {
    const response = await apiClient.get<{ success: boolean; data: GuildConfigData }>(
      `/api/guilds/${guildId}/config`
    );
    return response.data;
  },
  patchGuildConfig: async (guildId: string, update: GuildConfigUpdateRequest) => {
    const response = await apiClient.patch<{ success: boolean; data: GuildConfigData }>(
      `/api/guilds/${guildId}/config`,
      update
    );
    return response.data;
  },
  getDiscordRoles: async (guildId: string) => {
    const response = await apiClient.get<{ success: boolean; roles: GuildRole[] }>(
      `/api/guilds/${guildId}/roles/discord`
    );
    return response.data;
  },
  getDiscordChannels: async (guildId: string) => {
    const response = await apiClient.get<{ success: boolean; channels: DiscordChannel[] }>(
      `/api/guilds/${guildId}/channels/discord`
    );
    return response.data;
  },
  getBotRoleSettings: async (guildId: string) => {
    const response = await apiClient.get<BotRoleSettingsPayload>(
      `/api/guilds/${guildId}/settings/bot-roles`
    );
    return response.data;
  },
  updateBotRoleSettings: async (guildId: string, payload: BotRoleSettingsPayload) => {
    const response = await apiClient.put<BotRoleSettingsPayload>(
      `/api/guilds/${guildId}/settings/bot-roles`,
      payload
    );
    return response.data;
  },
  getBotChannelSettings: async (guildId: string) => {
    const response = await apiClient.get<BotChannelSettingsPayload>(
      `/api/guilds/${guildId}/settings/bot-channels`
    );
    return response.data;
  },
  updateBotChannelSettings: async (guildId: string, payload: BotChannelSettingsPayload) => {
    const response = await apiClient.put<BotChannelSettingsPayload>(
      `/api/guilds/${guildId}/settings/bot-channels`,
      payload
    );
    return response.data;
  },
  getVoiceSelectableRoles: async (guildId: string) => {
    const response = await apiClient.get<VoiceSelectableRolesPayload>(
      `/api/guilds/${guildId}/settings/voice/selectable-roles`
    );
    return response.data;
  },
  updateVoiceSelectableRoles: async (
    guildId: string,
    payload: VoiceSelectableRolesPayload
  ) => {
    const response = await apiClient.put<VoiceSelectableRolesPayload>(
      `/api/guilds/${guildId}/settings/voice/selectable-roles`,
      payload
    );
    return response.data;
  },
  getOrganizationSettings: async (guildId: string) => {
    const response = await apiClient.get<OrganizationSettingsPayload>(
      `/api/guilds/${guildId}/settings/organization`
    );
    return response.data;
  },
  updateOrganizationSettings: async (guildId: string, payload: OrganizationSettingsPayload) => {
    const response = await apiClient.put<OrganizationSettingsPayload>(
      `/api/guilds/${guildId}/settings/organization`,
      payload
    );
    return response.data;
  },
  validateOrganizationSid: async (guildId: string, sid: string) => {
    const response = await apiClient.post<OrganizationValidationResponse>(
      `/api/guilds/${guildId}/organization/validate-sid`,
      { sid }
    );
    return response.data;
  },
};
