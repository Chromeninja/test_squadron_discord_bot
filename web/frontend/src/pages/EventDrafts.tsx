import { Link } from 'react-router-dom';
import { Badge, Button, Card, CardBody } from '../components/ui';

interface EventDraftsProps {
  guildId: string;
}

function EventDrafts({ guildId }: EventDraftsProps) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <div className="overflow-hidden rounded-[28px] border border-[#ffbb00]/18 bg-[radial-gradient(circle_at_top_left,_rgba(255,187,0,0.16),_transparent_30%),linear-gradient(135deg,_rgba(12,12,12,0.98),_rgba(28,20,2,0.92))] p-6 shadow-2xl shadow-black/30">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[#ffbb00]/70">Draft Bay</p>
            <h2 className="mt-3 text-3xl font-bold text-[#fff4cc]">Drafts</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[#d6c7a3]">Draft save and restore is not available yet.</p>
          </div>
          <Badge variant="info">Guild {guildId}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card variant="default">
          <CardBody>
            <p className="text-xs uppercase tracking-[0.2em] text-[#ffcc4d]">Status</p>
            <h3 className="mt-2 text-xl font-semibold text-[#fff4cc]">No saved drafts</h3>
            <p className="mt-3 text-sm leading-6 text-[#d6c7a3]">Use the main Events page to create or edit live Discord scheduled events.</p>
          </CardBody>
        </Card>

        <Card variant="default">
          <CardBody>
            <p className="text-xs uppercase tracking-[0.2em] text-[#ffcc4d]">Next Step</p>
            <h3 className="mt-2 text-xl font-semibold text-[#fff4cc]">Return to Events</h3>
            <p className="mt-3 text-sm leading-6 text-[#d6c7a3]">Open the live event workspace to manage the current schedule.</p>
            <div className="mt-4">
              <Link to="/events">
                <Button variant="secondary" size="sm">Open Events Workspace</Button>
              </Link>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

export default EventDrafts;