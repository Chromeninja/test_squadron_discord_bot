import { Badge, Button, Modal, Spinner } from '../ui';
import { EnrichedUser, UserMetrics } from '../../api/endpoints';
import { OrgBadgeList } from './OrgBadgeList';
import { getStatusVariant } from '../../utils/statusHelpers';
import { formatDateValue, formatDuration } from '../../utils/format';
import { TIER_BADGE_COLORS, TIER_TEXT_COLORS } from '../../utils/tierColors';

function RoleBadgeList({ roles }: { roles: Array<{ id: number; name: string }> }) {
  if (roles.length === 0) {
    return <span className="text-gray-500">No roles</span>;
  }

  return (
    <div className="max-h-44 overflow-y-auto pr-1">
      <div className="flex flex-wrap gap-1.5">
        {roles.map((role) => (
          <span
            key={role.id}
            className="px-2 py-1 text-xs rounded bg-slate-700 text-gray-300 border border-slate-600"
            title={role.name}
          >
            {role.name}
          </span>
        ))}
      </div>
    </div>
  );
}

interface UserDetailsModalProps {
  open: boolean;
  user: EnrichedUser | null;
  isCrossGuild: boolean;
  onClose: () => void;
  userLoading?: boolean;
  userLoadError?: string | null;
  userMetrics: UserMetrics | null;
  userMetricsLoading: boolean;
  userMetricsError: string | null;
  canRecheck?: boolean;
  recheckingUserId?: string | null;
  onRecheck?: (userId: string) => void;
}

export function UserDetailsModal({
  open,
  user,
  isCrossGuild,
  onClose,
  userLoading = false,
  userLoadError = null,
  userMetrics,
  userMetricsLoading,
  userMetricsError,
  canRecheck = false,
  recheckingUserId = null,
  onRecheck,
}: UserDetailsModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Member Details"
      size="lg"
      headerVariant="default"
      footer={
        <div className="flex items-center justify-between w-full">
          <div>
            {user && !isCrossGuild && canRecheck && onRecheck && (
              <Button
                size="sm"
                onClick={() => onRecheck(user.discord_id)}
                loading={recheckingUserId === user.discord_id}
                title="Re-verify this user's RSI membership and update roles"
              >
                {recheckingUserId === user.discord_id
                  ? 'Rechecking...'
                  : 'Recheck Membership'}
              </Button>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      {userLoading && (
        <div className="flex items-center justify-center py-10 text-gray-500 text-sm">
          <Spinner className="mr-2 text-gray-400" label="Loading member details…" />
        </div>
      )}

      {!userLoading && userLoadError && (
        <div className="rounded-lg border border-amber-700/50 bg-amber-900/20 p-3 text-sm text-amber-300">
          {userLoadError}
        </div>
      )}

      {!userLoading && !userLoadError && user && (
        <>
          <div className="flex items-center gap-4 mb-6">
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.username}
                className="w-16 h-16 rounded-full"
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-slate-700 flex items-center justify-center text-gray-400 text-2xl font-bold">
                {user.username.charAt(0).toUpperCase()}
              </div>
            )}
            <div>
              <h4 className="text-lg font-semibold text-white">
                {user.global_name || user.username}
              </h4>
              <p className="text-sm text-gray-400">
                {user.username}#{user.discriminator}
              </p>
              <p className="text-xs text-gray-500 font-mono mt-0.5">{user.discord_id}</p>
            </div>
            <div className="ml-auto">
              <Badge variant={getStatusVariant(user.membership_status)}>
                {user.membership_status || 'unknown'}
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div className="bg-slate-900/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                RSI Handle
              </div>
              <div className="text-gray-200">
                {user.rsi_handle ? (
                  <a
                    href={`https://robertsspaceindustries.com/citizens/${user.rsi_handle}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 hover:underline"
                  >
                    {user.rsi_handle}
                  </a>
                ) : (
                  <span className="text-gray-500">—</span>
                )}
              </div>
            </div>

            {isCrossGuild && (
              <div className="bg-slate-900/50 rounded-lg p-3">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                  Guild
                </div>
                <div className="text-gray-200">
                  <Badge variant="purple" className="text-xs">
                    {user.guild_name || user.guild_id || 'Unknown'}
                  </Badge>
                </div>
              </div>
            )}

            <div className="bg-slate-900/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Main Organizations
              </div>
              <div className="mt-1">
                <OrgBadgeList orgs={user.main_orgs} colorScheme="blue" />
              </div>
            </div>

            <div className="bg-slate-900/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Affiliate Organizations
              </div>
              <div className="mt-1">
                <OrgBadgeList orgs={user.affiliate_orgs} colorScheme="green" />
              </div>
            </div>

            <div className="bg-slate-900/50 rounded-lg p-3 sm:col-span-2">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Roles</div>
              <div className="mt-1">
                <RoleBadgeList roles={user.roles} />
              </div>
            </div>

            <div className="bg-slate-900/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Joined Server
              </div>
              <div className="text-gray-200">{formatDateValue(user.joined_at)}</div>
            </div>
            <div className="bg-slate-900/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Account Created
              </div>
              <div className="text-gray-200">{formatDateValue(user.created_at)}</div>
            </div>
            <div className="bg-slate-900/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Last Verified
              </div>
              <div className="text-gray-200">{formatDateValue(user.last_updated)}</div>
            </div>
          </div>

          {userMetricsLoading && (
            <div className="mt-6 flex items-center justify-center py-6 text-gray-500 text-sm">
              <Spinner className="mr-2 text-gray-400" label="Loading metrics…" />
            </div>
          )}

          {!userMetricsLoading && userMetricsError && (
            <div className="mt-6 rounded-lg border border-amber-700/50 bg-amber-900/20 p-3 text-sm text-amber-300">
              {userMetricsError}
            </div>
          )}

          {!userMetricsLoading && userMetrics && (
            <div className="mt-6 space-y-4">
              <div className="bg-slate-900/50 rounded-lg p-4">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                  Activity Levels{' '}
                  <span className="normal-case text-gray-600">(last 30 days)</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { key: 'combined', label: 'Combined', icon: '⚡', tier: userMetrics.combined_tier },
                    { key: 'voice', label: 'Voice', icon: '🎤', tier: userMetrics.voice_tier },
                    { key: 'chat', label: 'Text', icon: '💬', tier: userMetrics.chat_tier },
                    { key: 'game', label: 'Gaming', icon: '🎮', tier: userMetrics.game_tier },
                  ].map(({ key, label, icon, tier }) => {
                    const t = tier ?? 'inactive';
                    // Split TIER_BADGE_COLORS to get border+bg portion only
                    const badgeColor = TIER_BADGE_COLORS[t] || TIER_BADGE_COLORS.inactive;
                    const textColor = TIER_TEXT_COLORS[t] || TIER_TEXT_COLORS.inactive;
                    return (
                      <div
                        key={key}
                        className={`rounded-lg border p-2.5 text-center ${badgeColor}`}
                      >
                        <div className="text-base mb-0.5">{icon}</div>
                        <div className="text-[10px] text-gray-400 uppercase tracking-wider">
                          {label}
                        </div>
                        <div className={`text-sm font-semibold capitalize ${textColor}`}>
                          {t}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="bg-slate-900/50 rounded-lg p-4">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                  Metrics Summary
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase">Messages</div>
                    <div className="text-lg font-bold text-white">
                      {userMetrics.total_messages.toLocaleString()}
                    </div>
                    <div className="text-[10px] text-gray-500">
                      {userMetrics.avg_messages_per_day.toFixed(1)}/day
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase">Voice Time</div>
                    <div className="text-lg font-bold text-white">
                      {formatDuration(userMetrics.total_voice_seconds)}
                    </div>
                    <div className="text-[10px] text-gray-500">
                      {formatDuration(userMetrics.avg_voice_per_day)}
                      /day
                    </div>
                  </div>
                  <div className="col-span-2">
                    <div className="text-[10px] text-gray-500 uppercase">Top Games</div>
                    {userMetrics.top_games.length > 0 ? (
                      <div className="mt-1 space-y-1">
                        {userMetrics.top_games.slice(0, 3).map((game, i) => (
                          <div
                            key={game.game_name}
                            className="flex items-center justify-between"
                          >
                            <span className="text-gray-300 truncate mr-2">
                              <span className="text-gray-500 text-[10px] mr-1">#{i + 1}</span>
                              {game.game_name}
                            </span>
                            <span className="text-indigo-400 text-xs font-medium whitespace-nowrap">
                              {formatDuration(game.total_seconds)}
                            </span>
                          </div>
                        ))}
                        {userMetrics.top_games.length > 3 && (
                          <div className="text-[10px] text-gray-600">
                            +{userMetrics.top_games.length - 3} more
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-gray-600 mt-1">No game activity</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
