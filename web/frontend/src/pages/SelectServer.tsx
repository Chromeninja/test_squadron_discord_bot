import { useCallback, useEffect, useState } from 'react';
import { authApi, GuildSummary } from '../api/endpoints';
import { handleApiError } from '../utils/toast';

interface SelectServerProps {
  onSelected: () => Promise<void> | void;
}

const SelectServer = ({ onSelected }: SelectServerProps) => {
  const [guilds, setGuilds] = useState<GuildSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const fetchGuilds = useCallback(async (forceRefresh = false) => {
    try {
      const response = await authApi.getGuilds(forceRefresh);
      setGuilds(response.guilds);
      setError(null);
    } catch (err) {
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
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="rounded-md bg-slate-700 px-4 py-2 font-semibold transition hover:bg-slate-600 disabled:cursor-not-allowed disabled:bg-slate-800"
          >
            {refreshing ? 'Refreshing...' : '🔄 Refresh Guild List'}
          </button>
          <button
            onClick={handleAddBot}
            className="rounded-md bg-green-700 px-4 py-2 font-semibold transition hover:bg-green-600"
          >
            ➕ Add Bot to Server
          </button>
          <button
            onClick={handleLogout}
            disabled={loggingOut}
            className="rounded-md bg-red-700 px-4 py-2 font-semibold transition hover:bg-red-600 disabled:cursor-not-allowed disabled:bg-red-900"
          >
            {loggingOut ? 'Logging out...' : '🚪 Logout'}
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-300">
            {error}
          </div>
        )}

        {guilds.length === 0 ? (
          <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-8 text-center text-gray-400">
            <p className="mb-4">No servers available. Make sure the bot is installed in your Discord server.</p>
            <p className="text-sm">Click "Add Bot to Server" above to invite the bot to your server.</p>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2">
            {guilds.map((guild) => (
              <div
                key={guild.guild_id}
                className="rounded-xl border border-slate-700 bg-slate-800/60 p-6 shadow hover:border-indigo-500 transition"
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
                  <div>
                    <h2 className="text-xl font-semibold">{guild.guild_name}</h2>
                    <p className="text-sm text-gray-400">Guild ID: {guild.guild_id}</p>
                  </div>
                </div>
                <button
                  onClick={() => handleSelect(guild.guild_id)}
                  disabled={selectingId === guild.guild_id}
                  className="w-full rounded-md bg-indigo-600 py-2 font-semibold transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-600"
                >
                  {selectingId === guild.guild_id ? 'Selecting...' : 'Go'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SelectServer;
