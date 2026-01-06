/**
 * API endpoint functions and types.
 */

import { apiClient } from './client';
import { RoleLevel } from '../utils/permissions';

// Types
export interface GuildPermission {
  guild_id: string;
  role_level: RoleLevel;
  source: string;
}

export interface UserProfile {
  user_id: string;
  username: string;
  discriminator: string;
  avatar: string | null;
  authorized_guilds: Record<string, GuildPermission>;
  active_guild_id?: string | null;
  is_admin?: boolean;
  is_moderator?: boolean;
  is_bot_owner?: boolean;  // True if user is the bot owner (global admin)
}

export interface GuildSummary {
  guild_id: string;
  guild_name: string;
  icon_url: string | null;
}

export interface GuildRole {
  id: string;
  name: string;
  color: number | null;
}

export interface GuildInfo {
  guild_id: string;
  guild_name: string;
  icon_url: string | null;
}

export interface DiscordChannel {
  id: string;
  name: string;
  category: string | null;
  position: number;
}

export interface RoleDelegationPolicyPayload {
  grantor_role_ids: string[];
  target_role_id: string;
  prerequisite_role_ids_all: string[];
  prerequisite_role_ids_any: string[];
  prerequisite_role_ids?: string[];
  enabled: boolean;
  note?: string | null;
}

export interface BotRoleSettingsPayload {
  bot_admins: string[];  // Bot admin roles
  discord_managers: string[];  // Discord manager roles (new)
  moderators: string[];  // Moderator roles
  staff: string[];  // Staff roles (new)
  bot_verified_role: string[];  // Base verification role (all verified users)
  main_role: string[];  // Verification role: full members
  affiliate_role: string[];  // Verification role: affiliate members
  nonmember_role: string[];  // Verification role: non-members

  delegation_policies?: RoleDelegationPolicyPayload[];  // DB-backed delegation policies
}

export interface BotChannelSettingsPayload {
  verification_channel_id: string | null;
  bot_spam_channel_id: string | null;
  public_announcement_channel_id: string | null;
  leadership_announcement_channel_id: string | null;
}

export interface BotChannelSettingsResponse extends BotChannelSettingsPayload {
  verification_message_updated?: boolean | null;
}

export interface VoiceSelectableRolesPayload {
  selectable_roles: string[];
}

export interface OrganizationSettingsPayload {
  organization_sid: string | null;
  organization_name: string | null;
  organization_logo_url: string | null;
}

export interface OrganizationValidationRequest {
  sid: string;
}

export interface OrganizationValidationResponse {
  success: boolean;
  is_valid: boolean;
  sid: string;
  organization_name: string | null;
  error: string | null;
}

export interface LogoValidationRequest {
  url: string;
}

export interface LogoValidationResponse {
  success: boolean;
  is_valid: boolean;
  url: string | null;
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
  user_id: string;
  rsi_handle: string;
  membership_status: string | null;
  community_moniker: string | null;
  last_updated: number;
  needs_reverify: boolean;
  main_orgs: string[] | null;
  affiliate_orgs: string[] | null;
}

export interface VoiceChannelRecord {
  id: string;
  guild_id: string;
  jtc_channel_id: string;
  owner_id: string;
  voice_channel_id: string;
  created_at: number;
  last_activity: number;
  is_active: boolean;
}

export interface VoiceChannelMember {
  user_id: string;
  username: string | null;
  display_name: string | null;
  rsi_handle: string | null;
  membership_status: string | null;
  is_owner: boolean;
}

export interface ActiveVoiceChannel {
  voice_channel_id: string;
  guild_id: string;
  jtc_channel_id: string;
  owner_id: string;
  owner_username: string | null;
  owner_rsi_handle: string | null;
  owner_membership_status: string | null;
  created_at: number;
  last_activity: number;
  channel_name: string | null;
  members: VoiceChannelMember[];
  // Cross-guild mode: guild name for display
  guild_name?: string | null;
}

// Cross-guild mode: voice channels grouped by guild
export interface GuildVoiceGroup {
  guild_id: string;
  guild_name: string;
  items: ActiveVoiceChannel[];
}

export interface PermissionEntry {
  target_id: string;
  target_type: string;
  permission: string;
  target_name?: string | null;
  is_everyone: boolean;
}

export interface PTTSettingEntry {
  target_id: string;
  target_type: string;
  ptt_enabled: boolean;
  target_name?: string | null;
  is_everyone: boolean;
}

export interface PrioritySpeakerEntry {
  target_id: string;
  target_type: string;
  priority_enabled: boolean;
  target_name?: string | null;
  is_everyone: boolean;
}

export interface SoundboardEntry {
  target_id: string;
  target_type: string;
  soundboard_enabled: boolean;
  target_name?: string | null;
  is_everyone: boolean;
}

export interface JTCChannelSettings {
  jtc_channel_id: string;
  jtc_channel_name: string | null;  // Friendly name of the JTC channel
  channel_name: string | null;
  user_limit: number | null;
  lock: boolean;
  permissions: PermissionEntry[];
  ptt_settings: PTTSettingEntry[];
  priority_settings: PrioritySpeakerEntry[];
  soundboard_settings: SoundboardEntry[];
}

export interface UserJTCSettings {
  user_id: string;
  rsi_handle: string | null;
  community_moniker: string | null;
  primary_jtc_id: string | null;
  jtcs: JTCChannelSettings[];
}

// Cross-guild mode: user voice settings grouped by guild
export interface GuildUserSettingsGroup {
  guild_id: string;
  guild_name: string;
  items: UserJTCSettings[];
}

export interface VoiceUserSettingsSearchResponse {
  success: boolean;
  items: UserJTCSettings[];
  total: number;
  page: number;
  page_size: number;
  message?: string | null;
  is_cross_guild?: boolean;
  guild_groups?: GuildUserSettingsGroup[] | null;
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
  // Cross-guild mode fields
  guild_id?: string | null;
  guild_name?: string | null;
}

export interface UsersListResponse {
  success: boolean;
  items: EnrichedUser[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  is_cross_guild?: boolean;
}

export interface ExportUsersRequest {
  membership_status?: string | null;
  membership_statuses?: string[] | null;
  role_ids?: number[] | null;
  selected_ids?: string[] | null;
  exclude_ids?: string[] | null;
}

// All Guilds metadata for cross-guild mode (bot owner only)
export interface AllGuildsMetadataResponse {
  success: boolean;
  guilds: Record<string, GuildSummary>;
}

// Sentinel value for "All Guilds" mode - must match backend
export const ALL_GUILDS_SENTINEL = '*';

// API functions
export const authApi = {
  getMe: async () => {
    const response = await apiClient.get<{ success: boolean; user: UserProfile | null }>('/api/auth/me');
    return response.data;
  },
  logout: async () => {
    const response = await apiClient.post('/api/auth/logout');
    return response.data;
  },
  getGuilds: async (forceRefresh: boolean = false) => {
    const response = await apiClient.get<{ success: boolean; guilds: GuildSummary[] }>(
      '/api/auth/guilds',
      {
        params: forceRefresh ? { force_refresh: '1' } : undefined,
      }
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
  // Bot owner only: get all guilds metadata for cross-guild label caching
  getAllGuildsMetadata: async (): Promise<AllGuildsMetadataResponse> => {
    const response = await apiClient.get<AllGuildsMetadataResponse>(
      '/api/auth/all-guilds-metadata'
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
      is_cross_guild?: boolean;
      guild_groups?: GuildVoiceGroup[] | null;
    }>('/api/voice/active');
    return response.data;
  },
  getIntegrity: async () => {
    const response = await apiClient.get<VoiceIntegrityResponse>(
      '/api/voice/integrity'
    );
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
  getUserSettings: async (query: string, page = 1, pageSize = 20) => {
    const response = await apiClient.get<VoiceUserSettingsSearchResponse>(
      '/api/voice/user-settings',
      {
        params: { query, page, page_size: pageSize },
      }
    );
    return response.data;
  },
  deleteUserVoiceSettings: async (userId: string, jtcChannelId?: string) => {
    const response = await apiClient.delete<VoiceSettingsResetResponse>(
      `/api/voice/user-settings/${userId}`,
      {
        params: jtcChannelId ? { jtc_channel_id: jtcChannelId } : {},
      }
    );
    return response.data;
  },
};

export interface VoiceSettingsResetResponse {
  success: boolean;
  message: string;
  channel_deleted: boolean;
  channel_id: number | null;
  deleted_counts: Record<string, number>;
}

export interface VoiceIntegrityResponse {
  count: number;
  details: string[];
}

export interface RecheckUserResponse {
  success: boolean;
  message: string;
  rsi_handle?: string | null;
  old_status?: string | null;
  new_status?: string | null;
  roles_updated?: boolean;
}

export interface ResetTimerResponse {
  success: boolean;
  message: string;
}

export interface BulkRecheckRequest {
  user_ids: string[];
}

export interface BulkRecheckResult {
  user_id: string;
  status: string;
  message: string;
  roles_updated: number;
  diff: Record<string, any>;
}

export interface BulkRecheckResponse {
  success: boolean;
  message: string;
  total: number;
  successful: number;
  failed: number;
  errors: Array<{ user_id: string; error: string }>;
  results: BulkRecheckResult[];
  summary_text: string | null;
  csv_filename: string | null;
  csv_content: string | null;
  job_id: string | null;
}

export interface BulkRecheckProgress {
  job_id: string;
  total: number;
  processed: number;
  successful: number;
  failed: number;
  status: 'running' | 'complete' | 'error';
  current_user: string | null;
  final_response?: BulkRecheckResponse | null;
}

export interface BulkRecheckStartResponse {
  job_id: string;
}

export const adminApi = {
  recheckUser: async (userId: string) => {
    const response = await apiClient.post<RecheckUserResponse>(
      `/api/admin/user/${userId}/recheck`
    );
    return response.data;
  },
  resetReverifyTimer: async (userId: string) => {
    const response = await apiClient.post<ResetTimerResponse>(
      `/api/admin/user/${userId}/reset-timer`
    );
    return response.data;
  },
  bulkRecheckUsers: async (userIds: string[]) => {
    const response = await apiClient.post<BulkRecheckResponse>(
      `/api/admin/users/bulk-recheck`,
      { user_ids: userIds }
    );
    return response.data;
  },
  startBulkRecheckUsers: async (userIds: string[]) => {
    const response = await apiClient.post<BulkRecheckStartResponse>(
      `/api/admin/users/bulk-recheck/start`,
      { user_ids: userIds }
    );
    return response.data;
  },
  getBulkRecheckProgress: async (jobId: string) => {
    const response = await apiClient.get<BulkRecheckProgress>(
      `/api/admin/users/bulk-recheck/${jobId}/progress`
    );
    return response.data;
  },
  leaveGuild: async (guildId: string) => {
    const response = await apiClient.post<{ success: boolean; guild_id: string; guild_name: string }>(
      `/api/guilds/${guildId}/leave`
    );
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
  exportBackendLogs: async (maxBytes: number = 1048576) => {
    const response = await apiClient.get('/api/logs/backend-export', {
      params: { max_bytes: maxBytes },
      responseType: 'blob',
    });
    
    // Trigger download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'backend.log.tail.txt');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
  exportAuditLogs: async (limit: number = 1000) => {
    const response = await apiClient.get('/api/logs/audit-export', {
      params: { limit },
      responseType: 'blob',
    });
    
    // Trigger download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    
    // Extract filename from Content-Disposition header if available
    const contentDisposition = response.headers['content-disposition'];
    let filename = 'audit_log.csv';
    if (contentDisposition) {
      const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
      if (matches != null && matches[1]) {
        filename = matches[1].replace(/['"]/g, '');
      }
    }
    
    link.setAttribute('download', filename);
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
    const response = await apiClient.put<BotChannelSettingsResponse>(
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
  validateLogoUrl: async (guildId: string, url: string) => {
    const response = await apiClient.post<LogoValidationResponse>(
      `/api/guilds/${guildId}/organization/validate-logo`,
      { url }
    );
    return response.data;
  },
};
