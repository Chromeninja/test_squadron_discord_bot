import { useCallback, useEffect, useState } from 'react';
import { authApi, adminApi, GuildSummary, UserProfile, ALL_GUILDS_SENTINEL } from '../api/endpoints';
import { handleApiError, showSuccess } from '../utils/toast';
import { Button, Card, Alert } from '../components/ui';

interface SelectServerProps {
  onSelected: () => Promise<void> | void;
  user?: UserProfile | null;
}

const SelectServer = ({ onSelected, user }: SelectServerProps) => {
  const [guilds, setGuilds] = useState<GuildSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [leavingId, setLeavingId] = useState<string | null>(null);
  const [confirmLeaveId, setConfirmLeaveId] = useState<string | null>(null);
  const [selectingAllGuilds, setSelectingAllGuilds] = useState(false);

  const isBotOwner = user?.is_bot_owner === true;

  const fetchGuilds = useCallback(async (forceRefresh = false) => {
    try {
      const response = await authApi.getGuilds(forceRefresh);
      setGuilds(response.guilds);
      setError(null);
    } catch (err: unknown) {
      // 401 errors are handled by the axios interceptor (redirect to login)
      // Don't show error message for those - just let the redirect happen
      const axiosError = err as { response?: { status?: number } };
      if (axiosError?.response?.status === 401) {
        return; // Interceptor will redirect to login
      }
      handleApiError(err, 'Unable to load your servers');
      setError('Unable to load your servers.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchGuilds();
  }, [fetchGuilds]);

  const handleSelect = async (guildId: string) => {
    setSelectingId(guildId);
    try {
      await authApi.selectGuild(guildId);
      await onSelected();
    } catch (err) {
      handleApiError(err, 'Failed to select server');
      setError('Failed to select server. Please try again.');
    } finally {
      setSelectingId(null);
    }
  };

  const handleSelectAllGuilds = async () => {
    setSelectingAllGuilds(true);
    try {
      await authApi.selectGuild(ALL_GUILDS_SENTINEL);
      await onSelected();
    } catch (err) {
      handleApiError(err, 'Failed to enter All Guilds mode');
      setError('Failed to enter All Guilds mode. Please try again.');
    } finally {
      setSelectingAllGuilds(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchGuilds(true);
  };

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await authApi.logout();
      window.location.href = '/';
    } catch (err) {
      handleApiError(err, 'Failed to log out');
    } finally {
      setLoggingOut(false);
    }
  };

  const handleAddBot = async () => {
    try {
      const response = await authApi.getBotInviteUrl();
      // Navigate to Discord authorization in the same window
      // Discord will redirect back to our bot-callback endpoint
      window.location.href = response.invite_url;
    } catch (err) {
      handleApiError(err, 'Failed to get bot invite URL');
      setError('Failed to get bot invite URL. Please try again.');
    }
  };

  const handleLeaveGuild = async (guildId: string, guildName: string) => {
    if (confirmLeaveId !== guildId) {
      // First click: show confirmation
      setConfirmLeaveId(guildId);
      return;
    }

    // Second click: perform leave
    setLeavingId(guildId);
    setConfirmLeaveId(null);
    try {
      await adminApi.leaveGuild(guildId);
      showSuccess(`Bot has left "${guildName}"`);
      // Refresh guild list
      await fetchGuilds(true);
    } catch (err) {
      handleApiError(err, 'Failed to leave server');
      setError('Failed to leave server. Please try again.');
    } finally {
      setLeavingId(null);
    }
  };

  const cancelLeave = () => {
    setConfirmLeaveId(null);
  };

  if (loading) {
    return (
      <div className="dashboard-theme flex min-h-screen items-center justify-center">
        <div className="text-xl text-[#d6c7a3]">Loading your servers...</div>
      </div>
    );
  }

  return (
    <div className="dashboard-theme min-h-screen text-[#f5deb3]">
      <div className="max-w-4xl mx-auto py-16 px-4">
        <h1 className="dashboard-title mb-4 text-3xl font-bold">Select a Server</h1>
        <p className="mb-8 text-[#a89465]">
          Choose the Discord server you want to manage. Only servers where the bot is installed are shown.
        </p>

        {/* Action buttons */}
        <div className="flex gap-4 mb-6">
          <Button
            variant="secondary"
            onClick={handleRefresh}
            loading={refreshing}
          >
            🔄 Refresh Guild List
          </Button>
          {isBotOwner && (
            <Button
              variant="success"
              onClick={handleAddBot}
              title="Add bot to a new server (bot owner only)"
            >
              ➕ Add Bot to Server
            </Button>
          )}
          <Button
            variant="danger"
            onClick={handleLogout}
            loading={loggingOut}
          >
            🚪 Logout
          </Button>
        </div>

        {error && (
          <Alert variant="error" className="mb-6">
            {error}
          </Alert>
        )}

        {guilds.length === 0 ? (
          <Card variant="ghost" padding="lg" className="text-center text-[#a89465]">
            <p className="mb-4">No servers available. Make sure the bot is installed in your Discord server.</p>
            <p className="text-sm">Click "Add Bot to Server" above to invite the bot to your server.</p>
          </Card>
        ) : (
          <div className="grid gap-6 md:grid-cols-2">
            {/* Bot Owner: All Guilds Mode Card */}
            {isBotOwner && (
              <Card
                padding="lg"
                hoverable
                className="border-2 border-[#ffbb00]/35 bg-[#ffbb00]/10 shadow-[0_0_26px_rgba(255,187,0,0.08)]"
              >
                <div className="flex items-center gap-4 mb-4">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full border border-[#ffbb00]/25 bg-[#ffbb00]/14 text-2xl text-[#fff1bf]">
                    🌐
                  </div>
                  <div className="flex-1">
                    <h2 className="text-xl font-semibold text-[#ffdd73]">All Guilds</h2>
                    <p className="text-sm text-[#c9b789]">View all users & voice data across all servers</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    fullWidth
                    variant="secondary"
                    onClick={handleSelectAllGuilds}
                    loading={selectingAllGuilds}
                    disabled={selectingId !== null || leavingId !== null}
                  >
                    {selectingAllGuilds ? 'Entering...' : '🔍 View All Guilds'}
                  </Button>
                </div>
                <p className="mt-2 text-center text-xs text-[#a89465]">
                  Bot Owner Only • Read-only cross-guild view
                </p>
              </Card>
            )}
            
            {guilds.map((guild) => (
              <Card
                key={guild.guild_id}
                padding="lg"
                hoverable
                className="shadow-[0_0_24px_rgba(0,0,0,0.22)]"
              >
                <div className="flex items-center gap-4 mb-4">
                  {guild.icon_url ? (
                    <img
                      src={guild.icon_url}
                      alt={guild.guild_name}
                      className="h-16 w-16 rounded-full border border-[#ffbb00]/18 object-cover"
                    />
                  ) : (
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[#17120a] text-2xl text-[#d6c7a3]">
                      {guild.guild_name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="flex-1">
                    <h2 className="text-xl font-semibold text-[#fff4cc]">{guild.guild_name}</h2>
                    <p className="text-sm text-[#a89465]">Guild ID: {guild.guild_id}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    fullWidth
                    onClick={() => handleSelect(guild.guild_id)}
                    loading={selectingId === guild.guild_id}
                    disabled={leavingId === guild.guild_id}
                  >
                    {selectingId === guild.guild_id ? 'Selecting...' : 'Go'}
                  </Button>
                  {isBotOwner && (
                    confirmLeaveId === guild.guild_id ? (
                      <div className="flex gap-1">
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => handleLeaveGuild(guild.guild_id, guild.guild_name)}
                          loading={leavingId === guild.guild_id}
                          title="Confirm leave"
                        >
                          ✓
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={cancelLeave}
                          disabled={leavingId === guild.guild_id}
                          title="Cancel"
                        >
                          ✕
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleLeaveGuild(guild.guild_id, guild.guild_name)}
                        disabled={leavingId !== null || selectingId !== null}
                        title="Leave this server (bot owner only)"
                      >
                        🚪
                      </Button>
                    )
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SelectServer;
