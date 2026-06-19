import { useState } from 'react';
import toast from 'react-hot-toast';
import { eventsApi, type EventRole } from '../../api/endpoints';
import { Badge, Button } from '../ui';
import { extractEventError } from './eventErrors';

interface EventRoleSignupListProps {
  guildId: string;
  eventId: string;
  roles: EventRole[];
  allowMultiple: boolean;
  signupsOpen: boolean;
  /** Whether the current user may join/leave roles (regular signup flow). */
  canModify: boolean;
  onChanged: () => void | Promise<void>;
}

/**
 * Read + signup view of an event's roles for regular members. Shows each role's
 * fill (count/capacity), locked state, and a Join/Leave control gated by the
 * same rules the backend enforces (locked, full, single-vs-multiple, open).
 */
export function EventRoleSignupList({
  guildId,
  eventId,
  roles,
  allowMultiple,
  signupsOpen,
  canModify,
  onChanged,
}: EventRoleSignupListProps) {
  const [busyRoleId, setBusyRoleId] = useState<number | null>(null);

  if (roles.length === 0) {
    return null;
  }

  const userRoleCount = roles.filter((role) => role.current_user_signed_up).length;

  const handleJoin = async (role: EventRole) => {
    setBusyRoleId(role.id);
    try {
      await eventsApi.signUpForRole(guildId, eventId, role.id);
      await onChanged();
    } catch (err) {
      toast.error(extractEventError(err, 'Could not sign up for that role.'));
    } finally {
      setBusyRoleId(null);
    }
  };

  const handleLeave = async (role: EventRole) => {
    setBusyRoleId(role.id);
    try {
      await eventsApi.withdrawFromRole(guildId, eventId, role.id);
      await onChanged();
    } catch (err) {
      toast.error(extractEventError(err, 'Could not leave that role.'));
    } finally {
      setBusyRoleId(null);
    }
  };

  return (
    <div className="space-y-2">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Roles</p>
      {roles.map((role) => {
        const isFull = role.capacity != null && role.signup_count >= role.capacity;
        const joined = role.current_user_signed_up;
        const blockedByMultiple = !allowMultiple && !joined && userRoleCount > 0;
        const disableJoin = !signupsOpen || role.locked || isFull || blockedByMultiple;

        return (
          <div
            key={role.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {role.emoji ? <span aria-hidden>{role.emoji}</span> : null}
                <span className="truncate text-sm font-medium text-[#f5deb3]">{role.name}</span>
                {role.locked ? <Badge variant="neutral">Locked</Badge> : null}
              </div>
              {role.description ? (
                <p className="truncate text-xs text-[#a89465]">{role.description}</p>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="text-xs text-[#f5deb3]">
                {role.signup_count}
                {role.capacity != null ? `/${role.capacity}` : ''}
              </span>
              {canModify ? (
                joined ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={busyRoleId === role.id}
                    onClick={() => void handleLeave(role)}
                  >
                    Leave
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={disableJoin}
                    loading={busyRoleId === role.id}
                    onClick={() => void handleJoin(role)}
                  >
                    Join
                  </Button>
                )
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default EventRoleSignupList;
