import { useState } from 'react';
import toast from 'react-hot-toast';
import { Badge, Button, Input, Textarea } from '../ui';

export interface DraftRole {
  name: string;
  emoji: string;
  description: string;
  capacity: string;
  locked: boolean;
}

interface EventDraftRoleListProps {
  roles: DraftRole[];
  onChange: (roles: DraftRole[]) => void;
}

const EMPTY_ROLE: DraftRole = {
  name: '',
  emoji: '',
  description: '',
  capacity: '',
  locked: false,
};

/**
 * Local-state role management for event creation. Renders draft roles
 * and provides a form to add new ones before the event is created.
 */
export function EventDraftRoleList({ roles, onChange }: EventDraftRoleListProps) {
  const [draft, setDraft] = useState<DraftRole>(EMPTY_ROLE);

  const handleAdd = () => {
    if (!draft.name.trim()) {
      toast.error('Role name is required.');
      return;
    }

    if (draft.capacity.trim()) {
      const capacity = Number(draft.capacity);
      if (!Number.isInteger(capacity) || capacity < 1) {
        toast.error('Capacity must be a positive whole number.');
        return;
      }
    }

    onChange([...roles, { ...draft, name: draft.name.trim() }]);
    setDraft(EMPTY_ROLE);
  };

  const handleToggleLock = (index: number) => {
    const updated = [...roles];
    updated[index] = { ...updated[index], locked: !updated[index].locked };
    onChange(updated);
  };

  const handleDelete = (index: number) => {
    onChange(roles.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3 rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/40 p-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Signup roles</p>
        <p className="text-xs text-[#a89465]">These roles will be created with your event.</p>
      </div>

      {roles.length > 0 ? (
        <div className="space-y-2">
          {roles.map((role, index) => (
            <div
              key={index}
              className="flex items-center justify-between gap-3 rounded-xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/60 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {role.emoji ? <span aria-hidden>{role.emoji}</span> : null}
                  <span className="truncate text-sm font-medium text-[#f5deb3]">{role.name}</span>
                  {role.locked ? <Badge variant="neutral">Locked</Badge> : null}
                </div>
                <p className="text-xs text-[#a89465]">
                  {role.capacity ? `Up to ${role.capacity}` : 'Unlimited'} capacity
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => handleToggleLock(index)}
                >
                  {role.locked ? 'Unlock' : 'Lock'}
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => handleDelete(index)}
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
        <Button variant="primary" onClick={() => void handleAdd()}>
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

export default EventDraftRoleList;
