import { Link } from 'react-router-dom';
import { Badge, Button, Card, CardBody } from '../components/ui';

interface EventRecurringProps {
  guildId: string;
}

function EventRecurring({ guildId }: EventRecurringProps) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="overflow-hidden rounded-[28px] border border-[#ffbb00]/18 bg-[radial-gradient(circle_at_top_left,_rgba(255,187,0,0.16),_transparent_30%),linear-gradient(135deg,_rgba(12,12,12,0.98),_rgba(28,20,2,0.92))] p-6 shadow-2xl shadow-black/30">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[#ffbb00]/70">Cadence Matrix</p>
            <h2 className="mt-3 text-3xl font-bold text-[#fff4cc]">Recurring Events</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[#d6c7a3]">Recurring scheduling is not available yet.</p>
          </div>
          <Badge variant="info">Guild {guildId}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card variant="default">
          <CardBody>
            <p className="text-xs uppercase tracking-[0.2em] text-[#ffcc4d]">Status</p>
            <h3 className="mt-2 text-xl font-semibold text-[#fff4cc]">No recurring schedules</h3>
            <p className="mt-3 text-sm leading-6 text-[#d6c7a3]">The dashboard does not store recurring event rules yet.</p>
          </CardBody>
        </Card>
        <Card variant="default">
          <CardBody>
            <p className="text-xs uppercase tracking-[0.2em] text-[#ffcc4d]">Next Step</p>
            <h3 className="mt-2 text-xl font-semibold text-[#fff4cc]">Use the live event builder</h3>
            <p className="mt-3 text-sm leading-6 text-[#d6c7a3]">Create individual Discord scheduled events from the main Events page.</p>
          </CardBody>
        </Card>
      </div>

      <Link to="/events">
        <Button variant="secondary" size="sm">Back to Events Workspace</Button>
      </Link>
    </div>
  );
}

export default EventRecurring;