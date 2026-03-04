/** Ticket statistics display cards. */

import { Card, CardBody } from '../../components/ui';

interface TicketStatsProps {
  open: number;
  closed: number;
  total: number;
}

export default function TicketStats({ open, closed, total }: TicketStatsProps) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:gap-4">
      <Card variant="default">
        <CardBody className="text-center px-2 py-3 sm:px-4 sm:py-4">
          <p className="text-2xl sm:text-3xl font-bold text-blue-400 leading-tight">{open}</p>
          <p className="text-xs sm:text-sm text-gray-400 mt-1 leading-tight">Open Tickets</p>
        </CardBody>
      </Card>
      <Card variant="default">
        <CardBody className="text-center px-2 py-3 sm:px-4 sm:py-4">
          <p className="text-2xl sm:text-3xl font-bold text-green-400 leading-tight">{closed}</p>
          <p className="text-xs sm:text-sm text-gray-400 mt-1 leading-tight">Closed Tickets</p>
        </CardBody>
      </Card>
      <Card variant="default">
        <CardBody className="text-center px-2 py-3 sm:px-4 sm:py-4">
          <p className="text-2xl sm:text-3xl font-bold text-gray-300 leading-tight">{total}</p>
          <p className="text-xs sm:text-sm text-gray-400 mt-1 leading-tight">Total Tickets</p>
        </CardBody>
      </Card>
    </div>
  );
}
