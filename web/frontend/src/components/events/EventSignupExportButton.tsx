import { useState } from 'react';
import toast from 'react-hot-toast';
import { eventsApi } from '../../api/endpoints';
import { Button } from '../ui';
import { extractEventError } from './eventErrors';

interface EventSignupExportButtonProps {
  guildId: string;
  eventId: string;
}

/** Coordinator-only CSV export of an event's web signups. */
export function EventSignupExportButton({ guildId, eventId }: EventSignupExportButtonProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      await eventsApi.exportSignups(guildId, eventId);
    } catch (err) {
      toast.error(extractEventError(err, 'Could not export signups.'));
    } finally {
      setExporting(false);
    }
  };

  return (
    <Button size="sm" variant="secondary" loading={exporting} onClick={() => void handleExport()}>
      Export CSV
    </Button>
  );
}

export default EventSignupExportButton;
