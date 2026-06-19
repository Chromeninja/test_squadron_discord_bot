import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { eventsApi, type EventRole, type ScheduledEventSummary } from '../../api/endpoints';
import { Button } from '../ui';
import { EventRoleSignupList } from './EventRoleSignupList';
import { extractEventError } from './eventErrors';

interface EventSignupPanelProps {
  guildId: string;
  event: ScheduledEventSummary;
  /** Whether the current user may sign up (regular members; not past events). */
  canSignup: boolean;
  onChanged: () => void | Promise<void>;
}

/**
 * Member-facing signup panel: whole-event interest toggle plus the role signup
 * list. Visible to every guild member for active/upcoming/recurring events.
 */
export function EventSignupPanel({ guildId, event, canSignup, onChanged }: EventSignupPanelProps) {
  const [roles, setRoles] = useState<EventRole[]>([]);
  const [allowMultiple, setAllowMultiple] = useState(event.allow_multiple_roles);
  const [signupsOpen, setSignupsOpen] = useState(
    event.signups_enabled && !event.signups_closed,
  );
  const [busy, setBusy] = useState(false);

  const loadRoles = useCallback(async () => {
    try {
      const res = await eventsApi.getRoles(guildId, event.id);
      setRoles(res.roles);
      setAllowMultiple(res.allow_multiple_roles);
      setSignupsOpen(res.signups_enabled && !res.signups_closed);
    } catch {
      // Roles are optional; a failure here should not break the card.
    }
  }, [guildId, event.id]);

  useEffect(() => {
    void loadRoles();
  }, [loadRoles]);

  const refresh = useCallback(async () => {
    await loadRoles();
    await onChanged();
  }, [loadRoles, onChanged]);

  const toggleInterest = async () => {
    setBusy(true);
    try {
      if (event.current_user_signed_up) {
        await eventsApi.withdrawInterest(guildId, event.id);
      } else {
        await eventsApi.markInterest(guildId, event.id);
      }
      await refresh();
    } catch (err) {
      toast.error(extractEventError(err, 'Could not update your interest.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Web interest</p>
          <p className="text-sm font-medium text-[#f5deb3]">
            {event.web_signup_count} interested
          </p>
        </div>
        {canSignup ? (
          <Button
            size="sm"
            variant={event.current_user_signed_up ? 'secondary' : 'primary'}
            loading={busy}
            disabled={!signupsOpen && !event.current_user_signed_up}
            onClick={() => void toggleInterest()}
          >
            {event.current_user_signed_up ? 'Remove Interest' : "I'm Interested"}
          </Button>
        ) : null}
      </div>

      {!signupsOpen && canSignup ? (
        <p className="text-xs text-[#a89465]">Signups are currently closed for this event.</p>
      ) : null}

      <EventRoleSignupList
        guildId={guildId}
        eventId={event.id}
        roles={roles}
        allowMultiple={allowMultiple}
        signupsOpen={signupsOpen}
        canModify={canSignup}
        onChanged={refresh}
      />
    </div>
  );
}

export default EventSignupPanel;
