/**
 * API endpoint functions and types.
 */

import { apiClient } from './client';
import { RoleLevel } from '../utils/permissions';
import { triggerBlobDownload, extractFilename } from '../utils/download';

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

export interface MetricsSettingsPayload {
  excluded_channel_ids: string[];
  tracked_games_mode?: string;
  tracked_games?: string[];
  min_voice_minutes?: number;
  min_game_minutes?: number;
  min_messages?: number;
}

export interface NewMemberRoleSettingsPayload {
  enabled: boolean;
  role_id: string | null;
  duration_days: number;
  max_server_age_days: number | null;
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
  metrics: MetricsSettingsPayload;
  organization: OrganizationSettingsPayload;
  read_only?: ReadOnlyYamlConfig | null;
}

export interface GuildConfigUpdateRequest {
  roles?: BotRoleSettingsPayload;
  channels?: BotChannelSettingsPayload;
  voice?: VoiceSelectableRolesPayload;
  metrics?: MetricsSettingsPayload;
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
  // Whether this channel is managed (JTC) by the bot
  is_managed?: boolean;
  // Discord channel type (2=voice, 13=stage)
  channel_type?: number | null;
  // Discord category name
  category?: string | null;
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

export interface UserDetailsResponse {
  success: boolean;
  data: EnrichedUser;
}

export interface ExportUsersRequest {
  membership_status?: string | null;
  membership_statuses?: string[] | null;
  role_ids?: number[] | null;
  selected_ids?: string[] | null;
  exclude_ids?: string[] | null;
  search?: string | null;
  orgs?: string[] | null;
}

export interface ResolveIdsRequest {
  membership_statuses?: string[] | null;
  search?: string | null;
  orgs?: string[] | null;
  exclude_ids?: string[] | null;
  limit?: number | null;
}

export interface ResolveIdsResponse {
  user_ids: string[];
  total: number;
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

// ============================================================================
// Metrics types
// ============================================================================

export interface MetricsLive {
  messages_today: number;
  active_voice_users: number;
  active_game_sessions: number;
  top_game: string | null;
}

export interface MetricsPeriod {
  total_messages: number;
  unique_messagers: number;
  avg_messages_per_user: number;
  total_voice_seconds: number;
  unique_voice_users: number;
  avg_voice_per_user: number;
  unique_users: number;
  top_games: GameStatsEntry[];
}

export interface MetricsOverview {
  live: MetricsLive;
  period: MetricsPeriod;
}

export interface VoiceLeaderboardEntry {
  user_id: string;
  total_seconds: number;
  username?: string | null;
  avatar_url?: string | null;
}

export interface MessageLeaderboardEntry {
  user_id: string;
  total_messages: number;
  username?: string | null;
  avatar_url?: string | null;
}

export interface GameStatsEntry {
  game_name: string;
  total_seconds: number;
  session_count: number;
  avg_seconds: number;
  unique_players?: number;
}

export interface TimeSeriesPoint {
  timestamp: number;
  value?: number;
  unique_users?: number;
  top_game?: string;
}

export interface UserGameStats {
  game_name: string;
  total_seconds: number;
}

export interface UserTimeSeriesPoint {
  timestamp: number;
  messages: number;
  voice_seconds: number;
}

export interface UserMetrics {
  user_id: string;
  username?: string | null;
  avatar_url?: string | null;
  total_messages: number;
  total_voice_seconds: number;
  avg_messages_per_day: number;
  avg_voice_per_day: number;
  top_games: UserGameStats[];
  timeseries: UserTimeSeriesPoint[];
  voice_tier?: string | null;
  chat_tier?: string | null;
  game_tier?: string | null;
  combined_tier?: string | null;
  last_voice_at?: number | null;
  last_chat_at?: number | null;
  last_game_at?: number | null;
}

export type ActivityDimension = 'all' | 'voice' | 'chat' | 'game';
export type ActivityTier = 'hardcore' | 'regular' | 'casual' | 'reserve' | 'inactive';

export interface ActivityTierCounts {
  hardcore: number;
  regular: number;
  casual: number;
  reserve: number;
  inactive: number;
}

export interface ActivityGroupCounts {
  all: ActivityTierCounts;
  voice: ActivityTierCounts;
  chat: ActivityTierCounts;
  game: ActivityTierCounts;
}

export interface ActivityGroupCountsResponse {
  success: boolean;
  data: ActivityGroupCounts;
}

// ============================================================================
// Metrics API
// ============================================================================

export const metricsApi = {
  getOverview: async (days: number = 7, dimension?: ActivityDimension | ActivityDimension[], tier?: ActivityTier | ActivityTier[]) => {
    const params: Record<string, any> = { days };
    if (dimension) params.dimension = Array.isArray(dimension) ? dimension.join(',') : dimension;
    if (tier) params.tier = Array.isArray(tier) ? tier.join(',') : tier;
    const response = await apiClient.get<{ success: boolean; data: MetricsOverview }>(
      '/api/metrics/overview',
      { params }
    );
    return response.data;
  },

  getVoiceLeaderboard: async (days: number = 7, limit: number = 10, dimension?: ActivityDimension | ActivityDimension[], tier?: ActivityTier | ActivityTier[]) => {
    const params: Record<string, any> = { days, limit };
    if (dimension) params.dimension = Array.isArray(dimension) ? dimension.join(',') : dimension;
    if (tier) params.tier = Array.isArray(tier) ? tier.join(',') : tier;
    const response = await apiClient.get<{ success: boolean; entries: VoiceLeaderboardEntry[] }>(
      '/api/metrics/voice/leaderboard',
      { params }
    );
    return {
      ...response.data,
      entries: (response.data.entries || []).map((entry) => ({
        ...entry,
        user_id: String((entry as any).user_id),
      })),
    };
  },

  getMessageLeaderboard: async (days: number = 7, limit: number = 10, dimension?: ActivityDimension | ActivityDimension[], tier?: ActivityTier | ActivityTier[]) => {
    const params: Record<string, any> = { days, limit };
    if (dimension) params.dimension = Array.isArray(dimension) ? dimension.join(',') : dimension;
    if (tier) params.tier = Array.isArray(tier) ? tier.join(',') : tier;
    const response = await apiClient.get<{ success: boolean; entries: MessageLeaderboardEntry[] }>(
      '/api/metrics/messages/leaderboard',
      { params }
    );
    return {
      ...response.data,
      entries: (response.data.entries || []).map((entry) => ({
        ...entry,
        user_id: String((entry as any).user_id),
      })),
    };
  },

  getTopGames: async (days: number = 7, limit: number = 10, dimension?: ActivityDimension | ActivityDimension[], tier?: ActivityTier | ActivityTier[]) => {
    const params: Record<string, any> = { days, limit };
    if (dimension) params.dimension = Array.isArray(dimension) ? dimension.join(',') : dimension;
    if (tier) params.tier = Array.isArray(tier) ? tier.join(',') : tier;
    const response = await apiClient.get<{ success: boolean; games: GameStatsEntry[] }>(
      '/api/metrics/games/top',
      { params }
    );
    return response.data;
  },

  getTimeSeries: async (metric: string = 'messages', days: number = 7, dimension?: ActivityDimension | ActivityDimension[], tier?: ActivityTier | ActivityTier[]) => {
    const params: Record<string, any> = { metric, days };
    if (dimension) params.dimension = Array.isArray(dimension) ? dimension.join(',') : dimension;
    if (tier) params.tier = Array.isArray(tier) ? tier.join(',') : tier;
    const response = await apiClient.get<{ success: boolean; metric: string; days: number; data: TimeSeriesPoint[] }>(
      '/api/metrics/timeseries',
      { params }
    );
    return response.data;
  },

  getUserMetrics: async (userId: string, days: number = 7) => {
    const response = await apiClient.get<{ success: boolean; data: UserMetrics }>(
      `/api/metrics/user/${userId}`,
      { params: { days } }
    );
    return response.data;
  },

  getActivityGroups: async (
    days: number = 7,
    dimension?: ActivityDimension | ActivityDimension[],
    tier?: ActivityTier | ActivityTier[]
  ) => {
    const params: Record<string, any> = { days };
    if (dimension) params.dimension = Array.isArray(dimension) ? dimension.join(',') : dimension;
    if (tier) params.tier = Array.isArray(tier) ? tier.join(',') : tier;
    const response = await apiClient.get<ActivityGroupCountsResponse>(
      '/api/metrics/activity-groups',
      { params }
    );
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
    membershipStatuses?: string[] | null,
    search?: string | null,
    orgs?: string[] | null,
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

    if (search && search.trim()) {
      params.search = search.trim();
    }

    if (orgs && orgs.length > 0) {
      params.orgs = orgs.join(',');
    }

    const response = await apiClient.get<UsersListResponse>('/api/users', { params });
    return response.data;
  },

  getUserDetails: async (discordId: string): Promise<UserDetailsResponse> => {
    const response = await apiClient.get<UserDetailsResponse>(
      `/api/users/detail/${discordId}`
    );
    return response.data;
  },

  getAvailableOrgs: async (): Promise<{ success: boolean; orgs: string[] }> => {
    const response = await apiClient.get<{ success: boolean; orgs: string[] }>('/api/users/orgs');
    return response.data;
  },

  exportUsers: async (filters: ExportUsersRequest): Promise<void> => {
    const response = await apiClient.post('/api/users/export', filters, {
      responseType: 'blob',
    });

    const filename = extractFilename(
      response.headers['content-disposition'],
      'members_export.csv',
    );
    triggerBlobDownload(response.data, filename);
  },

  resolveFilteredIds: async (filters: ResolveIdsRequest): Promise<ResolveIdsResponse> => {
    const response = await apiClient.post<ResolveIdsResponse>(
      '/api/users/resolve-ids',
      filters,
    );
    return response.data;
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

    triggerBlobDownload(response.data, 'bot.log.tail.txt');
  },
  exportBackendLogs: async (maxBytes: number = 1048576) => {
    const response = await apiClient.get('/api/logs/backend-export', {
      params: { max_bytes: maxBytes },
      responseType: 'blob',
    });

    triggerBlobDownload(response.data, 'backend.log.tail.txt');
  },
  exportAuditLogs: async (limit: number = 1000) => {
    const response = await apiClient.get('/api/logs/audit-export', {
      params: { limit },
      responseType: 'blob',
    });

    const filename = extractFilename(
      response.headers['content-disposition'],
      'audit_log.csv',
    );
    triggerBlobDownload(response.data, filename);
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
  getNewMemberRoleSettings: async (guildId: string) => {
    const response = await apiClient.get<NewMemberRoleSettingsPayload>(
      `/api/guilds/${guildId}/settings/new-member-role`
    );
    return response.data;
  },
  updateNewMemberRoleSettings: async (
    guildId: string,
    payload: NewMemberRoleSettingsPayload
  ) => {
    const response = await apiClient.put<NewMemberRoleSettingsPayload>(
      `/api/guilds/${guildId}/settings/new-member-role`,
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

// ---------------------------------------------------------------------------
// Tickets
// ---------------------------------------------------------------------------

export interface TicketCategory {
  id: number;
  guild_id: string;
  name: string;
  description: string;
  welcome_message: string;
  role_ids: string[];
  allowed_statuses: TicketCategoryEligibilityStatus[];
  emoji: string | null;
  sort_order: number;
  created_at: number;
  channel_id: string;
}

export type TicketCategoryEligibilityStatus =
  | 'bot_verified'
  | 'org_main'
  | 'org_affiliate';

export interface TicketCategoryCreate {
  guild_id: string;
  name: string;
  description?: string;
  welcome_message?: string;
  role_ids?: string[];
  allowed_statuses?: TicketCategoryEligibilityStatus[];
  emoji?: string | null;
  channel_id?: string;
}

export interface TicketCategoryUpdate {
  name?: string;
  description?: string;
  welcome_message?: string;
  role_ids?: string[];
  allowed_statuses?: TicketCategoryEligibilityStatus[];
  emoji?: string | null;
  sort_order?: number;
}

export interface TicketInfo {
  id: number;
  guild_id: string;
  channel_id: string;
  thread_id: string;
  user_id: string;
  category_id: number | null;
  status: string;
  closed_by: string | null;
  created_at: number;
  closed_at: number | null;
}

export interface TicketSettings {
  channel_id: string | null;
  panel_message_id: string | null;
  log_channel_id: string | null;
  close_message: string | null;
  staff_roles: string[];
  default_welcome_message: string | null;
}

export interface TicketSettingsUpdate {
  channel_id?: string | null;
  log_channel_id?: string | null;
  close_message?: string | null;
  staff_roles?: string[];
  default_welcome_message?: string | null;
}

export interface TicketChannelConfig {
  id: number;
  guild_id: string;
  channel_id: string;
  panel_title: string;
  panel_description: string;
  panel_color: string;
  button_text: string;
  button_emoji: string | null;
  enable_public_button: boolean;
  public_button_text: string;
  public_button_emoji: string | null;
  private_button_color: string | null;
  public_button_color: string | null;
  button_order: string;
  sort_order: number;
  created_at: number;
}

export interface TicketChannelConfigCreate {
  guild_id: string;
  channel_id: string;
  panel_title?: string | null;
  panel_description?: string | null;
  panel_color?: string | null;
  button_text?: string | null;
  button_emoji?: string | null;
  enable_public_button?: boolean | null;
  public_button_text?: string | null;
  public_button_emoji?: string | null;
  private_button_color?: string | null;
  public_button_color?: string | null;
  button_order?: string | null;
}

export interface TicketChannelConfigUpdate {
  new_channel_id?: string | null;  // Change the Discord channel assignment
  panel_title?: string | null;
  panel_description?: string | null;
  panel_color?: string | null;
  button_text?: string | null;
  button_emoji?: string | null;
  enable_public_button?: boolean | null;
  public_button_text?: string | null;
  public_button_emoji?: string | null;
  private_button_color?: string | null;
  public_button_color?: string | null;
  button_order?: string | null;
}

export interface TicketFormQuestion {
  id?: number;
  question_id: string;
  label: string;
  input_type?: 'text';
  options?: Array<{ value: string; label: string }>;
  placeholder?: string;
  style?: 'short' | 'paragraph';
  required?: boolean;
  min_length?: number | null;
  max_length?: number | null;
  sort_order?: number;
}

export interface TicketFormStep {
  id?: number;
  step_number: number;
  title: string;
  questions: TicketFormQuestion[];
}

export interface TicketFormConfig {
  category_id: number;
  steps: TicketFormStep[];
}

export interface TicketFormConfigUpdate {
  steps: TicketFormStep[];
}

export interface TicketFormValidation {
  success: boolean;
  valid: boolean;
  errors: string[];
}

export const ticketsApi = {
  getSettings: async () => {
    const response = await apiClient.get<{ success: boolean; settings: TicketSettings }>(
      '/api/tickets/settings'
    );
    return response.data;
  },

  updateSettings: async (payload: TicketSettingsUpdate) => {
    const response = await apiClient.put<{ success: boolean }>(
      '/api/tickets/settings',
      payload
    );
    return response.data;
  },

  deployPanel: async () => {
    const response = await apiClient.post<{ success: boolean; message_id: string }>(
      '/api/tickets/deploy-panel'
    );
    return response.data;
  },

  getChannelConfigs: async () => {
    const response = await apiClient.get<{ success: boolean; channels: TicketChannelConfig[] }>(
      '/api/tickets/channels'
    );
    return response.data;
  },

  createChannelConfig: async (payload: TicketChannelConfigCreate) => {
    const response = await apiClient.post<{ success: boolean; channels: TicketChannelConfig[] }>(
      '/api/tickets/channels',
      payload
    );
    return response.data;
  },

  updateChannelConfig: async (channelId: string, payload: TicketChannelConfigUpdate) => {
    const response = await apiClient.put<{ success: boolean }>(
      `/api/tickets/channels/${channelId}`,
      payload
    );
    return response.data;
  },

  deleteChannelConfig: async (channelId: string) => {
    const response = await apiClient.delete<{ success: boolean }>(
      `/api/tickets/channels/${channelId}`
    );
    return response.data;
  },

  getCategories: async () => {
    const response = await apiClient.get<{ success: boolean; categories: TicketCategory[] }>(
      '/api/tickets/categories'
    );
    return response.data;
  },

  createCategory: async (payload: TicketCategoryCreate) => {
    const response = await apiClient.post<{ success: boolean; categories: TicketCategory[] }>(
      '/api/tickets/categories',
      payload
    );
    return response.data;
  },

  updateCategory: async (categoryId: number, payload: TicketCategoryUpdate) => {
    const response = await apiClient.put<{ success: boolean }>(
      `/api/tickets/categories/${categoryId}`,
      payload
    );
    return response.data;
  },

  deleteCategory: async (categoryId: number) => {
    const response = await apiClient.delete<{ success: boolean }>(
      `/api/tickets/categories/${categoryId}`
    );
    return response.data;
  },

  getCategoryForm: async (categoryId: number) => {
    const response = await apiClient.get<{ success: boolean; config: TicketFormConfig }>(
      `/api/tickets/categories/${categoryId}/form`
    );
    return response.data;
  },

  updateCategoryForm: async (
    categoryId: number,
    payload: TicketFormConfigUpdate
  ) => {
    const response = await apiClient.put<{ success: boolean; config: TicketFormConfig }>(
      `/api/tickets/categories/${categoryId}/form`,
      payload
    );
    return response.data;
  },

  deleteCategoryForm: async (categoryId: number) => {
    const response = await apiClient.delete<{ success: boolean; config: TicketFormConfig }>(
      `/api/tickets/categories/${categoryId}/form`
    );
    return response.data;
  },

  validateCategoryForm: async (categoryId: number) => {
    const response = await apiClient.get<TicketFormValidation>(
      `/api/tickets/categories/${categoryId}/form/validate`
    );
    return response.data;
  },

  listTickets: async (status?: string, page: number = 1, pageSize: number = 20) => {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const response = await apiClient.get<{
      success: boolean;
      items: TicketInfo[];
      total: number;
      page: number;
      page_size: number;
    }>('/api/tickets/list', { params });
    return response.data;
  },

  getStats: async () => {
    const response = await apiClient.get<{
      success: boolean;
      open: number;
      closed: number;
      total: number;
    }>('/api/tickets/stats');
    return response.data;
  },
};
