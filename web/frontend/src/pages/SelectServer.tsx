import { useCallback, useEffect, useState } from 'react';
import { authApi, adminApi, GuildSummary, UserProfile } from '../api/endpoints';
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
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-xl text-gray-300">Loading your servers...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <div className="max-w-4xl mx-auto py-16 px-4">
        <h1 className="text-3xl font-bold mb-4">Select a Server</h1>
        <p className="text-gray-400 mb-8">
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
          <Card variant="ghost" padding="lg" className="text-center text-gray-400">
            <p className="mb-4">No servers available. Make sure the bot is installed in your Discord server.</p>
            <p className="text-sm">Click "Add Bot to Server" above to invite the bot to your server.</p>
          </Card>
        ) : (
          <div className="grid gap-6 md:grid-cols-2">
            {guilds.map((guild) => (
              <Card
                key={guild.guild_id}
                padding="lg"
                hoverable
                className="shadow hover:border-indigo-500"
              >
                <div className="flex items-center gap-4 mb-4">
                  {guild.icon_url ? (
                    <img
                      src={guild.icon_url}
                      alt={guild.guild_name}
                      className="h-16 w-16 rounded-full border border-slate-600 object-cover"
                    />
                  ) : (
                    <div className="h-16 w-16 rounded-full bg-slate-700 flex items-center justify-center text-2xl text-gray-300">
                      {guild.guild_name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="flex-1">
                    <h2 className="text-xl font-semibold">{guild.guild_name}</h2>
                    <p className="text-sm text-gray-400">Guild ID: {guild.guild_id}</p>
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
