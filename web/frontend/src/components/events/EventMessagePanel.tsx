import { useState } from 'react';
import toast from 'react-hot-toast';
import {
  eventsApi,
  type DiscordChannel,
  type EventMessageTarget,
} from '../../api/endpoints';
import { Button, Textarea } from '../ui';
import { extractEventError } from './eventErrors';

interface EventMessagePanelProps {
  guildId: string;
  eventId: string;
  channels: DiscordChannel[];
}

const TARGET_OPTIONS: Array<{ value: EventMessageTarget; label: string }> = [
  { value: 'all', label: 'All interested users' },
  { value: 'no_role', label: 'Interested, no role' },
  { value: 'all_roles', label: 'All users in any role' },
];

const SELECT_CLASS =
  'w-full rounded-xl border border-[rgba(255,187,0,0.18)] bg-[#120d00]/60 px-3 py-2 text-sm text-[#f5deb3] focus:border-[#ffbb00] focus:outline-none';

/**
 * Coordinator-only panel to send a Discord channel message to a signup segment.
 * The bot validates and sends; the dashboard never DMs users.
 */
export function EventMessagePanel({ guildId, eventId, channels }: EventMessagePanelProps) {
  const [channelId, setChannelId] = useState('');
  const [target, setTarget] = useState<EventMessageTarget>('all');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!channelId) {
      toast.error('Choose a channel to send the message in.');
      return;
    }
    if (!message.trim()) {
      toast.error('Message cannot be empty.');
      return;
    }
    setSending(true);
    try {
      const res = await eventsApi.sendMessage(guildId, eventId, {
        channel_id: channelId,
        message: message.trim(),
        target,
      });
      toast.success(`Message sent to ${res.recipients} user(s).`);
      setMessage('');
    } catch (err) {
      toast.error(extractEventError(err, 'Could not send the message.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-3 rounded-2xl border border-[rgba(255,187,0,0.12)] bg-[#120d00]/40 p-4">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#a89465]">Message signups</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <select
          className={SELECT_CLASS}
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
        >
          <option value="">Select a channel…</option>
          {channels.map((channel) => (
            <option key={channel.id} value={channel.id}>
              #{channel.name}
            </option>
          ))}
        </select>
        <select
          className={SELECT_CLASS}
          value={target}
          onChange={(e) => setTarget(e.target.value as EventMessageTarget)}
        >
          {TARGET_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <Textarea
        placeholder="Message to send…"
        value={message}
        maxLength={2000}
        rows={3}
        onChange={(e) => setMessage(e.target.value)}
      />
      <div className="flex justify-end">
        <Button variant="primary" loading={sending} onClick={() => void handleSend()}>
          Send Message
        </Button>
      </div>
    </div>
  );
}

export default EventMessagePanel;
