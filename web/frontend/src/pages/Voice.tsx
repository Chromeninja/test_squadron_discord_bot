import { useState, useEffect } from 'react';
import { voiceApi, authApi, ActiveVoiceChannel, UserJTCSettings, JTCChannelSettings, VoiceSettingsResetResponse, UserProfile, GuildVoiceGroup, GuildUserSettingsGroup, ALL_GUILDS_SENTINEL } from '../api/endpoints';
import { hasPermission } from '../utils/permissions';
import { handleApiError } from '../utils/toast';
import {
  Button,
  Badge,
  StatusBadge,
  MembershipBadge,
  Input,
  Card,
  Alert,
  Banner,
  Modal,
  ModalFooter,
  CollapsibleCard,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeader,
  TableCell,
} from '../components/ui';

function Voice() {
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserJTCSettings[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [totalResults, setTotalResults] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // Active channels state
  const [activeChannels, setActiveChannels] = useState<ActiveVoiceChannel[]>([]);
  const [activeLoading, setActiveLoading] = useState(true);
  const [activeError, setActiveError] = useState<string | null>(null);
  // Use string for channel/user IDs to preserve 64-bit Discord snowflake precision
  const [expandedChannels, setExpandedChannels] = useState<Set<string>>(new Set());
  const [expandedUsers, setExpandedUsers] = useState<Set<string>>(new Set());

  // Integrity issues state
  const [integrityIssues, setIntegrityIssues] = useState<{ count: number; details: string[] }>({ count: 0, details: [] });
  const [showIntegrityModal, setShowIntegrityModal] = useState(false);

  // Cross-guild mode state - for grouping data by guild
  const [activeGuildGroups, setActiveGuildGroups] = useState<GuildVoiceGroup[] | null>(null);
  const [_searchGuildGroups, setSearchGuildGroups] = useState<GuildUserSettingsGroup[] | null>(null);

  // Reset confirmation modal state
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetTargetUser, setResetTargetUser] = useState<UserJTCSettings | null>(null);
  const [resetTargetJtc, setResetTargetJtc] = useState<string | null>(null);
  const [resetConfirmText, setResetConfirmText] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetSuccess, setResetSuccess] = useState<VoiceSettingsResetResponse | null>(null);

  // Check if in cross-guild (All Guilds) mode
  const isCrossGuildMode = userProfile?.active_guild_id === ALL_GUILDS_SENTINEL;

  // Check if user has moderator access (required for reset operations)
  // Disabled in cross-guild mode for safety
  const canReset = (() => {
    // Disable reset actions in cross-guild mode for safety
    if (isCrossGuildMode) {
      return false;
    }
    if (!userProfile?.active_guild_id || !userProfile.authorized_guilds) {
      return false;
    }
    const guildPerm = userProfile.authorized_guilds[userProfile.active_guild_id];
    return guildPerm && hasPermission(guildPerm.role_level, 'moderator');
  })();

  // Load user profile on mount
  useEffect(() => {
    const loadUserProfile = async () => {
      try {
        const response = await authApi.getMe();
        setUserProfile(response.user);
      } catch (err) {
        handleApiError(err, 'Failed to load user profile.');
      }
    };
    loadUserProfile();
  }, []);

  // Load active channels on mount
  useEffect(() => {
    loadActiveChannels();
  }, []);

  // Fetch integrity issues from backend
  useEffect(() => {
    const run = async () => {
      try {
        const data = await voiceApi.getIntegrity();
        setIntegrityIssues({ count: data.count, details: data.details || [] });
      } catch (e) {
        // If it fails, keep banner hidden
        setIntegrityIssues({ count: 0, details: [] });
      }
    };
    run();
  }, []);

  const loadActiveChannels = async () => {
    setActiveLoading(true);
    setActiveError(null);

    try {
      const data = await voiceApi.getActive();
      setActiveChannels(data.items);
      setActiveGuildGroups(data.guild_groups || null);
    } catch (err) {
      setActiveError('Failed to load active channels');
    } finally {
      setActiveLoading(false);
    }
  };

  const toggleChannel = (channelId: string) => {
    const newExpanded = new Set(expandedChannels);
    if (newExpanded.has(channelId)) {
      newExpanded.delete(channelId);
    } else {
      newExpanded.add(channelId);
    }
    setExpandedChannels(newExpanded);
  };

  const toggleUser = (userId: string) => {
    const newExpanded = new Set(expandedUsers);
    if (newExpanded.has(userId)) {
      newExpanded.delete(userId);
    } else {
      newExpanded.add(userId);
    }
    setExpandedUsers(newExpanded);
  };

  const handleSearch = async (page = 1) => {
    if (!searchQuery.trim()) {
      setSearchError('Please enter a Discord ID or RSI handle');
      return;
    }

    setSearchLoading(true);
    setSearchError(null);
    setCurrentPage(page);

    try {
      const data = await voiceApi.getUserSettings(searchQuery.trim(), page, pageSize);
      setSearchResults(data.items);
      setTotalResults(data.total);
      setSearchGuildGroups(data.guild_groups || null);
      if (data.message) {
        setSearchError(data.message);
      }
    } catch (err) {
      setSearchError('Failed to search user voice settings');
      setSearchResults([]);
      setTotalResults(0);
      setSearchGuildGroups(null);
    } finally {
      setSearchLoading(false);
    }
  };

  const openResetModal = (user: UserJTCSettings, jtcChannelId?: string) => {
    setResetTargetUser(user);
    setResetTargetJtc(jtcChannelId || null);
    setResetConfirmText('');
    setResetError(null);
    setResetSuccess(null);
    setShowResetModal(true);
  };

  const closeResetModal = () => {
    setShowResetModal(false);
    setResetTargetUser(null);
    setResetTargetJtc(null);
    setResetConfirmText('');
    setResetError(null);
    setResetSuccess(null);
  };

  const handleResetVoiceSettings = async () => {
    if (!resetTargetUser) return;

    const expectedConfirmation = resetTargetJtc ? 'RESET' : 'RESET ALL';
    if (resetConfirmText !== expectedConfirmation) {
      setResetError(`Please type "${expectedConfirmation}" to confirm`);
      return;
    }

    setResetLoading(true);
    setResetError(null);

    try {
      const response = await voiceApi.deleteUserVoiceSettings(
        resetTargetUser.user_id,
        resetTargetJtc || undefined
      );
      
      setResetSuccess(response);
      
      // Refresh search results after successful reset
      setTimeout(() => {
        closeResetModal();
        handleSearch(currentPage);
      }, 3000);
    } catch (err: any) {
      const status = err.response?.status;
      const message = status === 403 ? 'No access - moderator role required' : (err.response?.data?.detail || 'Failed to reset voice settings');
      setResetError(message);
    } finally {
      setResetLoading(false);
    }
  };

  const formatTargetName = (entry: { target_id: string; target_name?: string | null; is_everyone: boolean; target_type: string; unknown_role?: boolean }) => {
    if (entry.is_everyone) {
      return <span className="font-medium">Everyone</span>;
    }
    if (entry.unknown_role) {
      return (
        <Badge 
          variant="warning" 
          title="Stored ID does not match any role in this guild. Check DB integrity."
        >
          Unknown Role (ID: {entry.target_id})
        </Badge>
      );
    }
    if (entry.target_name) {
      return <span className="font-medium">{entry.target_name}</span>;
    }
    return <span className="text-gray-500 font-mono text-xs">ID: {entry.target_id}</span>;
  };

  const renderSettingsTable = <T extends { target_id: string; target_name?: string | null; is_everyone: boolean; target_type: string; unknown_role?: boolean }>(
    title: string,
    items: T[],
    renderValue: (item: T) => React.ReactNode,
    emptyMessage: string
  ) => {
    if (items.length === 0) {
      return (
        <div>
          <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{title}</h6>
          <p className="text-sm text-gray-500 italic py-2">{emptyMessage}</p>
        </div>
      );
    }

    return (
      <div>
        <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{title}</h6>
        <Table>
          <TableHead>
            <TableRow noHover>
              <TableHeader>Target</TableHeader>
              <TableHeader className="w-24">Type</TableHeader>
              <TableHeader className="w-32">Setting</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item, idx) => (
              <TableRow key={idx}>
                <TableCell>{formatTargetName(item)}</TableCell>
                <TableCell>
                  <span className="text-xs text-gray-400">{item.target_type}</span>
                </TableCell>
                <TableCell>{renderValue(item)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  };

  const renderJTCSettings = (jtc: JTCChannelSettings, isPrimary: boolean) => {
    return (
      <Card variant="dark" padding="md">
        {/* JTC Header */}
        <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-700">
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-gray-500">JTC Channel</span>
              {jtc.jtc_channel_name && !jtc.jtc_channel_name.match(/^(JTC \d+|Channel \d+)$/) ? (
                <>
                  <span className="font-medium text-indigo-300">{jtc.jtc_channel_name}</span>
                  <span className="font-mono text-xs text-gray-500">ID: {jtc.jtc_channel_id}</span>
                </>
              ) : (
                <>
                  <span className="font-mono text-sm text-indigo-400">{jtc.jtc_channel_id}</span>
                  <Badge variant="warning-outline" title="Channel name could not be resolved">
                    Channel Not Found
                  </Badge>
                </>
              )}
              {isPrimary && (
                <Badge variant="primary-outline" title="Most recently used JTC channel">
                  Last Used
                </Badge>
              )}
            </div>
          </div>
          {canReset && (
            <Button
              variant="warning"
              size="sm"
              onClick={() => {
                const user = searchResults.find(u => u.jtcs.some(j => j.jtc_channel_id === jtc.jtc_channel_id));
                if (user) openResetModal(user, jtc.jtc_channel_id);
              }}
              title="Reset settings for this JTC only"
            >
              Reset JTC Settings
            </Button>
          )}
        </div>

        {/* Basic Settings - Compact Grid */}
        <div className="grid grid-cols-3 gap-x-6 gap-y-2 mb-4 text-sm">
          <div>
            <dt className="text-xs text-gray-500">Channel Name</dt>
            <dd className="font-medium text-gray-200 mt-0.5">
              {jtc.channel_name || <span className="text-gray-500 italic">Not set</span>}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">User Limit</dt>
            <dd className="font-medium text-gray-200 mt-0.5">
              {jtc.user_limit !== null && jtc.user_limit !== undefined ? jtc.user_limit : <span className="text-gray-500 italic">None</span>}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Lock Status</dt>
            <dd className="mt-0.5">
              <StatusBadge status={jtc.lock} trueLabel="Locked" falseLabel="Unlocked" />
            </dd>
          </div>
        </div>

        {/* Settings Sections */}
        <div className="space-y-4">
          {renderSettingsTable(
            'Permissions',
            jtc.permissions,
            (perm) => <span className="font-medium text-gray-300">{perm.permission}</span>,
            'No custom permissions configured'
          )}

          {renderSettingsTable(
            'Push-to-Talk',
            jtc.ptt_settings,
            (ptt) => <StatusBadge status={ptt.ptt_enabled} trueLabel="Enabled" falseLabel="Disabled" />,
            'No custom push-to-talk settings configured'
          )}

          {renderSettingsTable(
            'Priority Speaker',
            jtc.priority_settings,
            (priority) => <StatusBadge status={priority.priority_enabled} trueLabel="Enabled" falseLabel="Disabled" />,
            'No custom priority speaker settings configured'
          )}

          {renderSettingsTable(
            'Soundboard',
            jtc.soundboard_settings,
            (soundboard) => <StatusBadge status={soundboard.soundboard_enabled} trueLabel="Enabled" falseLabel="Disabled" />,
            'No custom soundboard settings configured'
          )}
        </div>
      </Card>
    );
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Cross-Guild Mode Alert */}
      {isCrossGuildMode && (
        <Alert variant="info" className="mb-6">
          <strong>🌐 All Guilds Mode</strong> — Viewing voice data across all servers.
          Member lists are not shown in this view. Reset actions are disabled. Switch to a specific server to manage settings.
        </Alert>
      )}

      {/* Integrity Banner */}
      {integrityIssues.count > 0 && (
        <Banner variant="warning" maxWidth="4xl">
          <strong>{integrityIssues.count} corrupted role IDs detected.</strong>{' '}
          <button
            onClick={() => setShowIntegrityModal(true)}
            className="text-yellow-300 underline cursor-pointer hover:text-yellow-200"
            title="View details"
          >
            View details
          </button>
        </Banner>
      )}

      <h2 className="text-2xl font-bold mb-6">Voice Channels</h2>

      {/* Active Channels List */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold">Active Voice Channels</h3>
          <Button variant="link" size="sm" onClick={loadActiveChannels}>
            Refresh
          </Button>
        </div>

        {activeLoading && (
          <Card padding="lg" className="text-center">
            <p className="text-gray-400">Loading active channels...</p>
          </Card>
        )}

        {activeError && (
          <Alert variant="error" className="mb-4">
            {activeError}
          </Alert>
        )}

        {!activeLoading && !activeError && activeChannels.length === 0 && (
          <Card padding="lg" className="text-center">
            <p className="text-gray-400">No active voice channels</p>
          </Card>
        )}

        {/* Render active channels - grouped by guild in cross-guild mode */}
        {!activeLoading && activeChannels.length > 0 && (
          <div className="space-y-4">
            {isCrossGuildMode && activeGuildGroups ? (
              // Cross-guild mode: render grouped by guild
              activeGuildGroups.map((group) => (
                <div key={group.guild_id} className="mb-6">
                  <div className="flex items-center gap-2 mb-3">
                    <Badge variant="purple">{group.guild_name}</Badge>
                    <span className="text-sm text-gray-400">
                      {group.items.length} active channel{group.items.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="space-y-2 ml-2 border-l-2 border-purple-800/50 pl-4">
                    {group.items.map((channel) => (
                      <CollapsibleCard
                        key={channel.voice_channel_id}
                        expanded={expandedChannels.has(channel.voice_channel_id)}
                        onToggle={() => toggleChannel(channel.voice_channel_id)}
                        header={
                          <div className="text-left">
                            <p className="font-medium">
                              {channel.channel_name || `Channel ${channel.voice_channel_id}`}
                            </p>
                            <p className="text-sm text-gray-400">
                              Channel ID: {channel.voice_channel_id} • Owner: {channel.owner_rsi_handle || `User ${channel.owner_id}`}
                            </p>
                          </div>
                        }
                        headerRight={
                          <div className="flex items-center gap-4">
                            <span className="text-sm text-gray-400">
                              {channel.members.length} {channel.members.length === 1 ? 'member' : 'members'}
                            </span>
                            <span className="text-sm text-gray-400">
                              {new Date(channel.last_activity * 1000).toLocaleString()}
                            </span>
                          </div>
                        }
                      >
                        <h4 className="font-medium mb-3">Members:</h4>
                        
                        {channel.members.length === 0 ? (
                          <p className="text-sm text-gray-400 italic">
                            Member list not available in All Guilds view. Switch to this server for real-time data.
                          </p>
                        ) : (
                          <div className="space-y-1">
                            {channel.members.map((member) => (
                              <div
                                key={member.user_id}
                                className="flex items-center gap-3 py-1.5 px-2 hover:bg-slate-800 rounded text-sm"
                              >
                                <span className="flex-1 font-medium">
                                  {member.display_name || member.rsi_handle || member.username || `User ${member.user_id}`}
                                </span>
                                <span className="text-gray-500">→</span>
                                <span className="font-mono text-gray-400 text-xs">{member.user_id}</span>
                                <span className="text-gray-500">-</span>
                                {member.is_owner && (
                                  <>
                                    <Badge variant="primary">Owner</Badge>
                                    <span className="text-gray-500">-</span>
                                  </>
                                )}
                                <MembershipBadge status={member.membership_status} />
                              </div>
                            ))}
                          </div>
                        )}
                      </CollapsibleCard>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              // Single guild mode: render flat list
              <div className="space-y-2">
                {activeChannels.map((channel) => (
                  <CollapsibleCard
                    key={channel.voice_channel_id}
                    expanded={expandedChannels.has(channel.voice_channel_id)}
                    onToggle={() => toggleChannel(channel.voice_channel_id)}
                    header={
                      <div className="text-left">
                        <p className="font-medium">
                          {channel.channel_name || `Channel ${channel.voice_channel_id}`}
                        </p>
                        <p className="text-sm text-gray-400">
                          Channel ID: {channel.voice_channel_id} • Owner: {channel.owner_rsi_handle || `User ${channel.owner_id}`}
                        </p>
                      </div>
                    }
                    headerRight={
                      <div className="flex items-center gap-4">
                        <span className="text-sm text-gray-400">
                          {channel.members.length} {channel.members.length === 1 ? 'member' : 'members'}
                        </span>
                        <span className="text-sm text-gray-400">
                          {new Date(channel.last_activity * 1000).toLocaleString()}
                        </span>
                      </div>
                    }
                  >
                    <h4 className="font-medium mb-3">Members:</h4>
                    
                    {channel.members.length === 0 ? (
                      <p className="text-sm text-gray-400 italic">
                        No members tracked (requires bot Gateway integration for real-time data)
                      </p>
                    ) : (
                      <div className="space-y-1">
                        {channel.members.map((member) => (
                          <div
                            key={member.user_id}
                            className="flex items-center gap-3 py-1.5 px-2 hover:bg-slate-800 rounded text-sm"
                          >
                            <span className="flex-1 font-medium">
                              {member.display_name || member.rsi_handle || member.username || `User ${member.user_id}`}
                            </span>
                            <span className="text-gray-500">→</span>
                            <span className="font-mono text-gray-400 text-xs">{member.user_id}</span>
                            <span className="text-gray-500">-</span>
                            {member.is_owner && (
                              <>
                                <Badge variant="primary">Owner</Badge>
                                <span className="text-gray-500">-</span>
                              </>
                            )}
                            <MembershipBadge status={member.membership_status} />
                          </div>
                        ))}
                      </div>
                    )}
                  </CollapsibleCard>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Search Section */}
      <div className="border-t border-slate-700 pt-8">
        <div className="max-w-6xl mx-auto">
          <h3 className="text-xl font-semibold mb-4">Search User Voice Settings</h3>

          {/* Search Bar */}
          <Card padding="md" className="mb-6">
            <div className="flex gap-4">
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search by Discord ID or RSI handle..."
                className="flex-1"
              />
              <Button
                onClick={() => handleSearch()}
                loading={searchLoading}
              >
                {searchLoading ? 'Searching...' : 'Search'}
              </Button>
            </div>
          </Card>

          {/* Error */}
          {searchError && (
            <Alert variant="error" className="mb-6">
              {searchError}
            </Alert>
          )}

          {/* Results */}
          {searchResults.length > 0 && (
            <div className="space-y-4">
              <div className="text-sm text-gray-400 mb-4">
                Found {totalResults} user{totalResults !== 1 ? 's' : ''} with saved voice settings
                {totalResults > pageSize && ` (showing page ${currentPage} of ${Math.ceil(totalResults / pageSize)})`}
              </div>

              {searchResults.map((user) => (
                <CollapsibleCard
                  key={user.user_id}
                  expanded={expandedUsers.has(user.user_id)}
                  onToggle={() => toggleUser(user.user_id)}
                  header={
                    <div className="text-left">
                      <p className="font-semibold text-lg">
                        {user.rsi_handle || `User ${user.user_id}`}
                      </p>
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-gray-500 font-mono">Discord ID: {user.user_id}</span>
                        {user.community_moniker && (
                          <>
                            <span className="text-gray-600">•</span>
                            <span className="text-gray-400">{user.community_moniker}</span>
                          </>
                        )}
                      </div>
                    </div>
                  }
                  headerRight={
                    <Badge variant={user.jtcs.length > 0 ? 'primary-outline' : 'neutral'}>
                      {user.jtcs.length} JTC{user.jtcs.length !== 1 ? 's' : ''}
                    </Badge>
                  }
                >
                  {/* Reset All Button */}
                  {canReset && (
                    <div className="flex justify-end mb-4">
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => openResetModal(user)}
                        title="Reset ALL voice settings for this user (guild-wide)"
                        leftIcon={
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                        }
                      >
                        Reset All Voice Settings
                      </Button>
                    </div>
                  )}

                  {user.jtcs.length === 0 ? (
                    <div className="text-center py-8">
                      <p className="text-gray-400 mb-1">No Saved Voice Settings</p>
                      <p className="text-sm text-gray-500">This user is verified but has no saved voice channel settings in this guild.</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {user.jtcs.map((jtc) => (
                        <div key={jtc.jtc_channel_id}>
                          {renderJTCSettings(jtc, jtc.jtc_channel_id === user.primary_jtc_id)}
                        </div>
                      ))}
                    </div>
                  )}
                </CollapsibleCard>
              ))}

              {/* Pagination */}
              {totalResults > pageSize && (
                <div className="flex justify-center gap-2 mt-6">
                  <Button
                    variant="secondary"
                    onClick={() => handleSearch(currentPage - 1)}
                    disabled={currentPage === 1 || searchLoading}
                  >
                    Previous
                  </Button>
                  <span className="px-4 py-2 bg-slate-800 rounded">
                    Page {currentPage} of {Math.ceil(totalResults / pageSize)}
                  </span>
                  <Button
                    variant="secondary"
                    onClick={() => handleSearch(currentPage + 1)}
                    disabled={currentPage >= Math.ceil(totalResults / pageSize) || searchLoading}
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* No results */}
          {!searchLoading && searchResults.length === 0 && searchQuery && !searchError && (
            <div className="text-center py-12">
              <p className="text-gray-400 text-lg mb-1">No users found</p>
              <p className="text-sm text-gray-500">No users matching "{searchQuery}" in this guild</p>
            </div>
          )}
        </div>
      </div>

      {/* Integrity Details Modal */}
      <Modal
        open={showIntegrityModal}
        onClose={() => setShowIntegrityModal(false)}
        title="Corrupted Role/ID Entries"
        size="lg"
        headerVariant="warning"
        footer={
          <Button variant="secondary" onClick={() => setShowIntegrityModal(false)}>
            Close
          </Button>
        }
      >
        <div className="space-y-3">
          {integrityIssues.details.length === 0 ? (
            <p className="text-sm text-gray-300">No details available.</p>
          ) : (
            <ul className="text-sm text-gray-200 space-y-2">
              {integrityIssues.details.map((line, idx) => (
                <li key={idx} className="bg-slate-900/50 rounded p-3 border border-slate-700 font-mono text-xs">
                  {line}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-gray-400">
            These IDs do not match any current roles/users/channels for this guild. Consider cleaning up orphaned JTC-scoped data.
          </p>
        </div>
      </Modal>

      {/* Reset Confirmation Modal */}
      <Modal
        open={showResetModal && resetTargetUser !== null}
        onClose={closeResetModal}
        title={resetTargetJtc ? 'Reset JTC Voice Settings' : 'Reset ALL Voice Settings'}
        size="lg"
        headerVariant={resetTargetJtc ? 'warning' : 'error'}
      >
        <div className="space-y-4">
          {!resetSuccess ? (
            <>
              {/* Warning */}
              <Alert variant={resetTargetJtc ? 'warning' : 'error'}>
                <p className="font-semibold mb-2">
                  {resetTargetJtc ? '⚠️ Warning - JTC Settings Reset' : '🚨 DESTRUCTIVE OPERATION WARNING'}
                </p>
                <p className="text-sm">
                  {resetTargetJtc 
                    ? `This will permanently delete voice settings for JTC ${resetTargetJtc} only.`
                    : 'This will permanently delete ALL voice settings for this user in this guild.'}
                </p>
              </Alert>

              {/* Target Info */}
              <Card variant="dark" padding="md">
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="text-gray-500">User:</span>
                    <span className="ml-2 font-medium">{resetTargetUser?.rsi_handle || `User ${resetTargetUser?.user_id}`}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Discord ID:</span>
                    <span className="ml-2 font-mono text-xs">{resetTargetUser?.user_id}</span>
                  </div>
                  {resetTargetJtc && (
                    <div>
                      <span className="text-gray-500">JTC Channel:</span>
                      <span className="ml-2 font-mono text-xs text-indigo-400">{resetTargetJtc}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">Scope:</span>
                    <Badge 
                      variant={resetTargetJtc ? 'warning-outline' : 'error-outline'}
                      className="ml-2"
                    >
                      {resetTargetJtc ? 'Single JTC' : 'Guild-Wide (All JTCs)'}
                    </Badge>
                  </div>
                </div>
              </Card>

              {/* What will be deleted */}
              <Card variant="dark" padding="md">
                <p className="text-sm font-semibold mb-2">This action will delete:</p>
                <ul className="text-sm text-gray-400 space-y-1 ml-4 list-disc">
                  {!resetTargetJtc && <li>User's active voice channel (if exists)</li>}
                  <li>Channel settings (name, limit, lock status)</li>
                  <li>Custom permissions</li>
                  <li>Push-to-talk settings</li>
                  <li>Priority speaker settings</li>
                  <li>Soundboard settings</li>
                </ul>
                <p className="text-sm text-yellow-400 mt-3">⚠️ This action cannot be undone!</p>
              </Card>

              {/* Confirmation Input */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  Type <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">{resetTargetJtc ? 'RESET' : 'RESET ALL'}</span> to confirm:
                </label>
                <Input
                  value={resetConfirmText}
                  onChange={(e) => setResetConfirmText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleResetVoiceSettings()}
                  placeholder={resetTargetJtc ? 'RESET' : 'RESET ALL'}
                  autoFocus
                />
              </div>

              {/* Error */}
              {resetError && (
                <Alert variant="error">
                  {resetError}
                </Alert>
              )}
            </>
          ) : (
            <>
              {/* Success Message */}
              <Alert variant="success" title="Reset Complete">
                {resetSuccess.message}
              </Alert>

              {/* Deletion Summary */}
              <Card variant="dark" padding="md">
                <p className="text-sm font-semibold mb-3">📊 Database Records Deleted:</p>
                <div className="space-y-1.5">
                  <div className="text-sm flex justify-between">
                    <span className="text-gray-400">Total:</span>
                    <span className="font-semibold">
                      {Object.values(resetSuccess.deleted_counts).reduce((a, b) => a + b, 0)} rows
                    </span>
                  </div>
                  {Object.entries(resetSuccess.deleted_counts).map(([table, count]) => (
                    count > 0 && (
                      <div key={table} className="text-sm flex justify-between pl-4">
                        <span className="text-gray-500">{table}:</span>
                        <span className="text-gray-300">{count}</span>
                      </div>
                    )
                  ))}
                </div>
              </Card>

              {/* Channel Action */}
              {resetSuccess.channel_id && (
                <Card variant="dark" padding="md">
                  <p className="text-sm font-semibold mb-2">🎤 Channel Action:</p>
                  {resetSuccess.channel_deleted ? (
                    <p className="text-sm text-green-400">
                      ✅ Deleted voice channel (ID: {resetSuccess.channel_id})
                    </p>
                  ) : (
                    <p className="text-sm text-yellow-400">
                      ⚠️ Channel {resetSuccess.channel_id} could not be deleted (may already be gone)
                    </p>
                  )}
                </Card>
              )}

              <p className="text-sm text-gray-400 text-center">Closing automatically and refreshing results...</p>
            </>
          )}
        </div>

        {/* Modal Footer */}
        <ModalFooter className="border-t border-slate-700 mt-4 -mx-6 -mb-4 px-6 py-4">
          {!resetSuccess ? (
            <>
              <Button
                variant="secondary"
                onClick={closeResetModal}
                disabled={resetLoading}
              >
                Cancel
              </Button>
              <Button
                variant={resetTargetJtc ? 'warning' : 'danger'}
                onClick={handleResetVoiceSettings}
                disabled={resetLoading || resetConfirmText !== (resetTargetJtc ? 'RESET' : 'RESET ALL')}
                loading={resetLoading}
              >
                {resetTargetJtc ? 'Reset JTC Settings' : 'Reset All Settings'}
              </Button>
            </>
          ) : (
            <Button onClick={closeResetModal}>
              Close
            </Button>
          )}
        </ModalFooter>
      </Modal>
    </div>
  );
}

export default Voice;
