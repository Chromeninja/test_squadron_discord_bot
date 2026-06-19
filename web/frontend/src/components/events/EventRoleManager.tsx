import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { eventsApi, type EventRole } from '../../api/endpoints';
import { Badge, Button, Input, Textarea } from '../ui';
import { extractEventError } from './eventErrors';

interface EventRoleManagerProps {
  guildId: string;
  eventId: string;
  onChanged: () => void | Promise<void>;
}

interface NewRoleState {
  name: string;
  emoji: string;
  description: string;
  capacity: string;
}

const EMPTY_ROLE: NewRoleState = { name: '', emoji: '', description: '', capacity: '' };

/**
 * Coordinator-only manager for an event's role slots: create, lock/unlock, and
 * delete roles. Capacity and ordering are set on creation; locking is toggled
 * inline.
 */
export function EventRoleManager({ guildId, eventId, onChanged }: EventRoleManagerProps) {
  const [roles, setRoles] = useState<EventRole[]>([]);
  const [draft, setDraft] = useState<NewRoleState>(EMPTY_ROLE);
  const [creating, setCreating] = useState(false);
  const [busyRoleId, setBusyRoleId] = useState<number | null>(null);

  const loadRoles = useCallback(async () => {
    try {
      const res = await eventsApi.getRoles(guildId, eventId);
      setRoles(res.roles);
    } catch (err) {
      toast.error(extractEventError(err, 'Could not load roles.'));
    }
  }, [guildId, eventId]);

  useEffect(() => {
    void loadRoles();
  }, [loadRoles]);

  const refresh = useCallback(async () => {
    await loadRoles();
    await onChanged();
  }, [loadRoles, onChanged]);

  const handleCreate = async () => {
    if (!draft.name.trim()) {
      toast.error('Role name is required.');
      return;
    }
    setCreating(true);
    try {
      await eventsApi.createRole(guildId, eventId, {
        name: draft.name.trim(),
        emoji: draft.emoji.trim() || null,
        description: draft.description.trim() || null,
        capacity: draft.capacity.trim() ? Number(draft.capacity) : null,
        sort_order: roles.length,
      });
      setDraft(EMPTY_ROLE);
      await refresh();
    } catch (err) {
      toast.error(extractEventError(err, 'Could not create role.'));
    } finally {
      setCreating(false);
    }
  };

  const handleToggleLock = async (role: EventRole) => {
    setBusyRoleId(role.id);
    try {
      await eventsApi.updateRole(guildId, eventId, role.id, { locked: !role.locked });
      await refresh();
    } catch (err) {
      toast.error(extractEventError(err, 'Could not update role.'));
    } finally {
      setBusyRoleId(null);
    }
  };

  const handleDelete = async (role: EventRole) => {
    setBusyRoleId(role.id);
    try {
      await eventsApi.deleteRole(guildId, eventId, role.id);
      await refresh();
    } catch (err) {
      toast.error(extractEventError(err, 'Could not delete role.'));
    } finally {
      setBusyRoleId(null);
    }
  };

  return (
    <div className="space-y-3 rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/40 p-4">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Manage roles</p>

      {roles.length > 0 ? (
        <div className="space-y-2">
          {roles.map((role) => (
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
                <p className="text-xs text-[#a89465]">
                  {role.signup_count}
                  {role.capacity != null ? `/${role.capacity}` : ''} signed up
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  loading={busyRoleId === role.id}
                  onClick={() => void handleToggleLock(role)}
                >
                  {role.locked ? 'Unlock' : 'Lock'}
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  loading={busyRoleId === role.id}
                  onClick={() => void handleDelete(role)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-[#a89465]">No roles yet. Add one below.</p>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
        <Input
          placeholder="Role name"
          value={draft.name}
          maxLength={40}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <Input
          placeholder="Emoji"
          value={draft.emoji}
          maxLength={32}
          onChange={(e) => setDraft({ ...draft, emoji: e.target.value })}
        />
        <Input
          placeholder="Capacity"
          type="number"
          min={1}
          value={draft.capacity}
          onChange={(e) => setDraft({ ...draft, capacity: e.target.value })}
        />
        <Button variant="primary" loading={creating} onClick={() => void handleCreate()}>
          Add Role
        </Button>
      </div>
      <Textarea
        placeholder="Role description (optional)"
        value={draft.description}
        maxLength={280}
        rows={2}
        onChange={(e) => setDraft({ ...draft, description: e.target.value })}
      />
    </div>
  );
}

export default EventRoleManager;
