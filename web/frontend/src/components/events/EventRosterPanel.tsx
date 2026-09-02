import { useCallback, useState } from 'react';
import toast from 'react-hot-toast';
import { eventsApi, type EventRoster } from '../../api/endpoints';
import { Badge, Button, CollapsibleCard, Spinner } from '../ui';
import { extractEventError } from './eventErrors';

interface EventRosterPanelProps {
  guildId: string;
  eventId: string;
  /** Discord native RSVP/interest count, shown separately from web signups. */
  discordUserCount: number;
}

function userLabel(user: { display_name: string | null; user_id: string }): string {
  return user.display_name || user.user_id;
}

/**
 * Coordinator-only roster: web signups broken out by role plus a separate
 * Discord RSVP count. Lazy-loads on expand. Web and Discord counts are never
 * merged.
 */
export function EventRosterPanel({ guildId, eventId, discordUserCount }: EventRosterPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [roster, setRoster] = useState<EventRoster | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyUser, setBusyUser] = useState<string | null>(null);

  const loadRoster = useCallback(async () => {
    setLoading(true);
    try {
      setRoster(await eventsApi.getRoster(guildId, eventId));
    } catch (err) {
      toast.error(extractEventError(err, 'Could not load the roster.'));
    } finally {
      setLoading(false);
    }
  }, [guildId, eventId]);

  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next && roster === null) {
      void loadRoster();
    }
  };

  const handleRemove = async (userId: string) => {
    setBusyUser(userId);
    try {
      setRoster(await eventsApi.removeUser(guildId, eventId, userId));
    } catch (err) {
      toast.error(extractEventError(err, 'Could not remove that user.'));
    } finally {
      setBusyUser(null);
    }
  };

  return (
    <CollapsibleCard
      expanded={expanded}
      onToggle={handleToggle}
      header={<span className="text-sm font-semibold text-[#fff4cc]">Roster &amp; attendees</span>}
      headerRight={
        <div className="flex items-center gap-2 text-xs text-[#a89465]">
          <Badge variant="neutral">Discord RSVP: {discordUserCount}</Badge>
          {roster ? <Badge variant="neutral">Web: {roster.total_web_signups}</Badge> : null}
        </div>
      }
    >
      {loading ? (
        <div className="flex justify-center py-4">
          <Spinner />
        </div>
      ) : roster ? (
        <div className="space-y-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">
              Interested, no role ({roster.no_role_users.length})
            </p>
            {roster.no_role_users.length === 0 ? (
              <p className="text-xs text-[#a89465]">Nobody yet.</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {roster.no_role_users.map((user) => (
                  <li
                    key={user.user_id}
                    className="flex items-center justify-between gap-2 text-sm text-[#f5deb3]"
                  >
                    <span className="truncate">{userLabel(user)}</span>
                    <Button
                      size="sm"
                      variant="danger"
                      loading={busyUser === user.user_id}
                      onClick={() => void handleRemove(user.user_id)}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {roster.roles.map((role) => (
            <div key={role.role_id}>
              <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">
                {role.emoji ? `${role.emoji} ` : ''}
                {role.name} ({role.users.length}
                {role.capacity != null ? `/${role.capacity}` : ''})
              </p>
              {role.users.length === 0 ? (
                <p className="text-xs text-[#a89465]">Nobody yet.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {role.users.map((user) => (
                    <li
                      key={`${role.role_id}-${user.user_id}`}
                      className="flex items-center justify-between gap-2 text-sm text-[#f5deb3]"
                    >
                      <span className="truncate">{userLabel(user)}</span>
                      <Button
                        size="sm"
                        variant="danger"
                        loading={busyUser === user.user_id}
                        onClick={() => void handleRemove(user.user_id)}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-[#a89465]">Expand to load the roster.</p>
      )}
    </CollapsibleCard>
  );
}

export default EventRosterPanel;
