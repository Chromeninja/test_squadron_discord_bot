/** Ticket statistics display cards. */

import { Card, CardBody } from '../../components/ui';

interface TicketStatsProps {
  open: number;
  closed: number;
  total: number;
}

export default function TicketStats({ open, closed, total }: TicketStatsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <Card variant="default">
        <CardBody className="text-center">
          <p className="text-3xl font-bold text-blue-400">{open}</p>
          <p className="text-sm text-gray-400 mt-1">Open Tickets</p>
        </CardBody>
      </Card>
      <Card variant="default">
        <CardBody className="text-center">
          <p className="text-3xl font-bold text-green-400">{closed}</p>
          <p className="text-sm text-gray-400 mt-1">Closed Tickets</p>
        </CardBody>
      </Card>
      <Card variant="default">
        <CardBody className="text-center">
          <p className="text-3xl font-bold text-gray-300">{total}</p>
          <p className="text-sm text-gray-400 mt-1">Total Tickets</p>
        </CardBody>
      </Card>
    </div>
  );
}
