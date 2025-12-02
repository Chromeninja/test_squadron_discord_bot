import { useState, useEffect } from 'react';
import { voiceApi, ActiveVoiceChannel, UserJTCSettings, JTCChannelSettings } from '../api/endpoints';

function Voice() {
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

  // Load active channels on mount
  useEffect(() => {
    loadActiveChannels();
  }, []);

  // Example: fetch integrity issues from backend (to be wired up)
  useEffect(() => {
    // TODO: Replace with real API call
    setIntegrityIssues({
      count: 3,
      details: [
        'channel_permissions rowid 42: ID 1313551309869416400',
        'channel_ptt_settings rowid 17: ID 1313551309869416400',
        'channel_settings rowid 5: ID 1313551309869416400',
      ],
    });
  }, []);

  const loadActiveChannels = async () => {
    setActiveLoading(true);
    setActiveError(null);

    try {
      const data = await voiceApi.getActive();
      setActiveChannels(data.items);
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
      if (data.message) {
        setSearchError(data.message);
      }
    } catch (err) {
      setSearchError('Failed to search user voice settings');
      setSearchResults([]);
      setTotalResults(0);
    } finally {
      setSearchLoading(false);
    }
  };

  const renderSettingBadge = (value: boolean, trueLabel: string, falseLabel: string) => {
    return (
      <span
        className={`px-2 py-0.5 text-xs font-semibold rounded ${
          value ? 'bg-green-900 text-green-200' : 'bg-gray-700 text-gray-300'
        }`}
      >
        {value ? trueLabel : falseLabel}
      </span>
    );
  };

  const renderIntegrityBanner = () => {
    if (integrityIssues.count === 0) return null;
    return (
      <div className="bg-yellow-900/80 text-yellow-200 px-4 py-2 rounded mb-4 max-w-4xl mx-auto flex items-center justify-between">
        <span>
          <strong>{integrityIssues.count} corrupted role IDs detected.</strong> <span className="text-yellow-300 underline cursor-pointer" title={integrityIssues.details.join('\n')}>View details</span>
        </span>
      </div>
    );
  };

  const formatTargetName = (entry: { target_id: string; target_name?: string | null; is_everyone: boolean; target_type: string; unknown_role?: boolean }) => {
    if (entry.is_everyone) {
      return (
        <span className="flex items-center gap-1.5">
          <span className="font-medium">Everyone</span>
          <span className="px-1.5 py-0.5 text-xs rounded bg-blue-900/50 text-blue-200 border border-blue-700">@everyone</span>
        </span>
      );
    }
    if (entry.unknown_role) {
      return (
        <span className="flex items-center gap-1.5">
          <span className="bg-yellow-900 text-yellow-200 px-2 py-0.5 rounded text-xs" title="Stored ID does not match any role in this guild. Check DB integrity.">Unknown Role (ID: {entry.target_id})</span>
        </span>
      );
    }
    if (entry.target_name) {
      return <span className="font-medium">{entry.target_name}</span>;
    }
    return <span className="text-gray-500 font-mono text-xs">ID: {entry.target_id}</span>;
  };

  const renderJTCSettings = (jtc: JTCChannelSettings, isPrimary: boolean) => {
    return (
      <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
        {/* JTC Header */}
        <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-700">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">JTC Channel</span>
              <span className="font-mono text-sm text-indigo-400">{jtc.jtc_channel_id}</span>
              {isPrimary && (
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-indigo-900/50 text-indigo-200 border border-indigo-700">
                  Primary
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Basic Settings - Compact Grid */}
        <div className="grid grid-cols-3 gap-x-6 gap-y-2 mb-4 text-sm">
          <div>
            <dt className="text-xs text-gray-500">Channel Name</dt>
            <dd className="font-medium text-gray-200 mt-0.5">{jtc.channel_name || <span className="text-gray-500 italic">Not set</span>}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">User Limit</dt>
            <dd className="font-medium text-gray-200 mt-0.5">
              {jtc.user_limit !== null && jtc.user_limit !== undefined ? jtc.user_limit : <span className="text-gray-500 italic">None</span>}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Lock Status</dt>
            <dd className="mt-0.5">{renderSettingBadge(jtc.lock, 'Locked', 'Unlocked')}</dd>
          </div>
        </div>

        {/* Settings Sections */}
        <div className="space-y-4">
          {/* Permissions */}
          {jtc.permissions.length > 0 ? (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Permissions</h6>
              <div className="bg-slate-800/50 rounded border border-slate-700 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-800/80 text-xs text-gray-400">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Target</th>
                      <th className="text-left px-3 py-2 font-medium w-24">Type</th>
                      <th className="text-left px-3 py-2 font-medium w-32">Permission</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {jtc.permissions.map((perm, idx) => (
                      <tr key={idx} className="hover:bg-slate-700/30">
                        <td className="px-3 py-2">{formatTargetName(perm)}</td>
                        <td className="px-3 py-2">
                          <span className="text-xs text-gray-400">{perm.target_type}</span>
                        </td>
                        <td className="px-3 py-2">
                          <span className="font-medium text-gray-300">{perm.permission}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Permissions</h6>
              <p className="text-sm text-gray-500 italic py-2">No custom permissions configured</p>
            </div>
          )}

          {/* PTT Settings */}
          {jtc.ptt_settings.length > 0 ? (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Push-to-Talk</h6>
              <div className="bg-slate-800/50 rounded border border-slate-700 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-800/80 text-xs text-gray-400">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Target</th>
                      <th className="text-left px-3 py-2 font-medium w-24">Type</th>
                      <th className="text-left px-3 py-2 font-medium w-32">Setting</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {jtc.ptt_settings.map((ptt, idx) => (
                      <tr key={idx} className="hover:bg-slate-700/30">
                        <td className="px-3 py-2">{formatTargetName(ptt)}</td>
                        <td className="px-3 py-2">
                          <span className="text-xs text-gray-400">{ptt.target_type}</span>
                        </td>
                        <td className="px-3 py-2">
                          {renderSettingBadge(ptt.ptt_enabled, 'Enabled', 'Disabled')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Push-to-Talk</h6>
              <p className="text-sm text-gray-500 italic py-2">No custom push-to-talk settings configured</p>
            </div>
          )}

          {/* Priority Speaker Settings */}
          {jtc.priority_settings.length > 0 ? (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Priority Speaker</h6>
              <div className="bg-slate-800/50 rounded border border-slate-700 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-800/80 text-xs text-gray-400">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Target</th>
                      <th className="text-left px-3 py-2 font-medium w-24">Type</th>
                      <th className="text-left px-3 py-2 font-medium w-32">Setting</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {jtc.priority_settings.map((priority, idx) => (
                      <tr key={idx} className="hover:bg-slate-700/30">
                        <td className="px-3 py-2">{formatTargetName(priority)}</td>
                        <td className="px-3 py-2">
                          <span className="text-xs text-gray-400">{priority.target_type}</span>
                        </td>
                        <td className="px-3 py-2">
                          {renderSettingBadge(priority.priority_enabled, 'Enabled', 'Disabled')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Priority Speaker</h6>
              <p className="text-sm text-gray-500 italic py-2">No custom priority speaker settings configured</p>
            </div>
          )}

          {/* Soundboard Settings */}
          {jtc.soundboard_settings.length > 0 ? (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Soundboard</h6>
              <div className="bg-slate-800/50 rounded border border-slate-700 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-800/80 text-xs text-gray-400">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Target</th>
                      <th className="text-left px-3 py-2 font-medium w-24">Type</th>
                      <th className="text-left px-3 py-2 font-medium w-32">Setting</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {jtc.soundboard_settings.map((soundboard, idx) => (
                      <tr key={idx} className="hover:bg-slate-700/30">
                        <td className="px-3 py-2">{formatTargetName(soundboard)}</td>
                        <td className="px-3 py-2">
                          <span className="text-xs text-gray-400">{soundboard.target_type}</span>
                        </td>
                        <td className="px-3 py-2">
                          {renderSettingBadge(soundboard.soundboard_enabled, 'Enabled', 'Disabled')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div>
              <h6 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Soundboard</h6>
              <p className="text-sm text-gray-500 italic py-2">No custom soundboard settings configured</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto">
      {renderIntegrityBanner()}

      <h2 className="text-2xl font-bold mb-6">Voice Channels</h2>

      {/* Active Channels List */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold">Active Voice Channels</h3>
          <button
            onClick={loadActiveChannels}
            className="text-sm text-indigo-400 hover:text-indigo-300"
          >
            Refresh
          </button>
        </div>

        {activeLoading && (
          <div className="bg-slate-800 rounded-lg p-8 text-center border border-slate-700">
            <p className="text-gray-400">Loading active channels...</p>
          </div>
        )}

        {activeError && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
            <p className="text-red-400">{activeError}</p>
          </div>
        )}

        {!activeLoading && !activeError && activeChannels.length === 0 && (
          <div className="bg-slate-800 rounded-lg p-8 text-center border border-slate-700">
            <p className="text-gray-400">No active voice channels</p>
          </div>
        )}

        {!activeLoading && activeChannels.length > 0 && (
          <div className="space-y-2">
            {activeChannels.map((channel) => (
              <div
                key={channel.voice_channel_id}
                className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden"
              >
                {/* Channel Header (Collapsible) */}
                <button
                  onClick={() => toggleChannel(channel.voice_channel_id)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700/50 transition"
                >
                  <div className="flex items-center gap-4">
                    <svg
                      className={`w-5 h-5 text-gray-400 transition-transform ${
                        expandedChannels.has(channel.voice_channel_id) ? 'rotate-90' : ''
                      }`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                    <div className="text-left">
                      <p className="font-medium">
                        {channel.channel_name || `Channel ${channel.voice_channel_id}`}
                      </p>
                      <p className="text-sm text-gray-400">
                        Channel ID: {channel.voice_channel_id} • Owner: {channel.owner_rsi_handle || `User ${channel.owner_id}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-400">
                      {channel.members.length} {channel.members.length === 1 ? 'member' : 'members'}
                    </span>
                    <span className="text-sm text-gray-400">
                      {new Date(channel.last_activity * 1000).toLocaleString()}
                    </span>
                  </div>
                </button>

                {/* Channel Details (Expanded) */}
                {expandedChannels.has(channel.voice_channel_id) && (
                  <div className="px-6 py-4 bg-slate-900/50 border-t border-slate-700">
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
                                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-indigo-900 text-indigo-200">
                                  Owner
                                </span>
                                <span className="text-gray-500">-</span>
                              </>
                            )}
                            {member.membership_status ? (
                              <span
                                className={`px-2 py-0.5 text-xs font-semibold rounded ${
                                  member.membership_status === 'main'
                                    ? 'bg-green-900 text-green-200'
                                    : member.membership_status === 'affiliate'
                                    ? 'bg-blue-900 text-blue-200'
                                    : member.membership_status === 'non_member'
                                    ? 'bg-gray-700 text-gray-300'
                                    : 'bg-gray-800 text-gray-400'
                                }`}
                              >
                                {member.membership_status === 'main'
                                  ? 'Main'
                                  : member.membership_status === 'affiliate'
                                  ? 'Affiliate'
                                  : member.membership_status === 'non_member'
                                  ? 'Not Member'
                                  : 'Unknown'}
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-gray-800 text-gray-500">
                                Not Verified
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search Section */}
      <div className="border-t border-slate-700 pt-8">
        {/* Max-width container for search results */}
        <div className="max-w-6xl mx-auto">
          <h3 className="text-xl font-semibold mb-4">Search User Voice Settings</h3>

          {/* Search Bar */}
          <div className="bg-slate-800 rounded-lg p-4 mb-6 border border-slate-700">
            <div className="flex gap-4">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search by Discord ID or RSI handle..."
                className="flex-1 bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
              />
              <button
                onClick={() => handleSearch()}
                disabled={searchLoading}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-600 px-6 py-2 rounded font-medium transition"
              >
                {searchLoading ? 'Searching...' : 'Search'}
              </button>
            </div>
          </div>

          {/* Error */}
          {searchError && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-6">
              <p className="text-red-400">{searchError}</p>
            </div>
          )}

          {/* Results */}
          {searchResults.length > 0 && (
            <div className="space-y-4">
              <div className="text-sm text-gray-400 mb-4">
                Found {totalResults} user{totalResults !== 1 ? 's' : ''} with saved voice settings
                {totalResults > pageSize && ` (showing page ${currentPage} of ${Math.ceil(totalResults / pageSize)})`}
              </div>

              {searchResults.map((user) => (
                <div
                  key={user.user_id}
                  className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden"
                >
                  {/* User Header */}
                  <button
                    onClick={() => toggleUser(user.user_id)}
                    className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700/50 transition"
                  >
                    <div className="flex items-center gap-4">
                      <svg
                        className={`w-5 h-5 text-gray-400 transition-transform ${
                          expandedUsers.has(user.user_id) ? 'rotate-90' : ''
                        }`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 5l7 7-7 7"
                        />
                      </svg>
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
                    </div>
                    <div className="text-sm">
                      <span className={`px-3 py-1 rounded font-medium ${
                        user.jtcs.length > 0 
                          ? 'bg-indigo-900/50 text-indigo-200 border border-indigo-700'
                          : 'bg-gray-700 text-gray-400'
                      }`}>
                        {user.jtcs.length} JTC{user.jtcs.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </button>

                  {/* User Settings Details (Expanded) */}
                  {expandedUsers.has(user.user_id) && (
                    <div className="px-6 py-4 bg-slate-900/50 border-t border-slate-700">
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
                    </div>
                  )}
                </div>
              ))}

            {/* Pagination */}
            {totalResults > pageSize && (
              <div className="flex justify-center gap-2 mt-6">
                <button
                  onClick={() => handleSearch(currentPage - 1)}
                  disabled={currentPage === 1 || searchLoading}
                  className="px-4 py-2 bg-slate-700 rounded hover:bg-slate-600 disabled:bg-slate-800 disabled:text-gray-600 transition"
                >
                  Previous
                </button>
                <span className="px-4 py-2 bg-slate-800 rounded">
                  Page {currentPage} of {Math.ceil(totalResults / pageSize)}
                </span>
                <button
                  onClick={() => handleSearch(currentPage + 1)}
                  disabled={currentPage >= Math.ceil(totalResults / pageSize) || searchLoading}
                  className="px-4 py-2 bg-slate-700 rounded hover:bg-slate-600 disabled:bg-slate-800 disabled:text-gray-600 transition"
                >
                  Next
                </button>
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
    </div>
  );
}

export default Voice;
