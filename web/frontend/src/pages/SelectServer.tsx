import { useEffect, useState } from 'react';
import { authApi, GuildSummary } from '../api/endpoints';

interface SelectServerProps {
  onSelected: () => Promise<void> | void;
}

const SelectServer = ({ onSelected }: SelectServerProps) => {
  const [guilds, setGuilds] = useState<GuildSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);

  useEffect(() => {
    const fetchGuilds = async () => {
      try {
        const response = await authApi.getGuilds();
        setGuilds(response.guilds);
        setError(null);
      } catch (err) {
        console.error(err);
        setError('Unable to load your servers.');
      } finally {
        setLoading(false);
      }
    };

    fetchGuilds();
  }, []);

  const handleSelect = async (guildId: string) => {
    setSelectingId(guildId);
    try {
      await authApi.selectGuild(guildId);
      await onSelected();
    } catch (err) {
      console.error(err);
      setError('Failed to select server. Please try again.');
    } finally {
      setSelectingId(null);
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

        {error && (
          <div className="mb-6 rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-300">
            {error}
          </div>
        )}

        {guilds.length === 0 ? (
          <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-8 text-center text-gray-400">
            No servers available. Make sure the bot is installed in your Discord server.
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
