/**
 * Shared OrgBadgeList component.
 *
 * Renders a list of organization badges with RSI links, an overflow
 * count chip, and a redacted-org count chip.  Used in both the Users
 * table and the UserDetailsModal.
 */

interface OrgBadgeListProps {
  orgs: string[] | null | undefined;
  maxVisible?: number;
  colorScheme?: 'blue' | 'green';
}

export function OrgBadgeList({
  orgs,
  maxVisible = Infinity,
  colorScheme = 'blue',
}: OrgBadgeListProps) {
  if (!orgs || orgs.length === 0) {
    return <span className="text-gray-500">-</span>;
  }

  const visible = orgs.filter((o) => o !== 'REDACTED');
  const redactedCount = orgs.length - visible.length;
  const shown = visible.slice(0, maxVisible);
  const overflowCount = visible.length - shown.length;

  const colors =
    colorScheme === 'green'
      ? 'bg-green-900/30 text-green-300 border-green-700/50 hover:bg-green-900/50 hover:border-green-600/70'
      : 'bg-blue-900/30 text-blue-300 border-blue-700/50 hover:bg-blue-900/50 hover:border-blue-600/70';

  return (
    <div className="flex flex-wrap gap-1 max-w-xs">
      {shown.map((org, idx) => (
        <a
          key={idx}
          href={`https://robertsspaceindustries.com/orgs/${org}`}
          target="_blank"
          rel="noopener noreferrer"
          className={`px-2 py-0.5 text-xs rounded border transition-colors cursor-pointer ${colors}`}
        >
          {org}
        </a>
      ))}
      {overflowCount > 0 && (
        <span
          className="px-2 py-0.5 text-xs rounded bg-slate-700 text-gray-400"
          title={visible.slice(maxVisible).join(', ')}
        >
          +{overflowCount}
        </span>
      )}
      {redactedCount > 0 && (
        <span
          className="px-2 py-0.5 text-xs rounded bg-slate-700 text-gray-400"
          title="Redacted organizations"
        >
          +{redactedCount} redacted
        </span>
      )}
    </div>
  );
}
