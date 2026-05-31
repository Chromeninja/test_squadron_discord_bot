import type { ReactNode } from 'react';
import { Card, CardBody } from '../components/ui';

interface EventPageHeaderProps {
  eyebrow?: string;
  title?: string;
  subtitle?: string | null;
  description?: string;
  actions?: ReactNode;
  footer?: ReactNode;
}

export function EventPageHeader({
  eyebrow = 'Workspace / Events',
  title,
  subtitle,
  description,
  actions,
  footer,
}: EventPageHeaderProps) {
  return (
    <div className="rounded-[28px] border border-[rgba(255,187,0,0.12)] bg-[radial-gradient(circle_at_top_left,_rgba(255,187,0,0.12),_transparent_28%),linear-gradient(180deg,rgba(20,23,31,0.97),rgba(11,14,20,0.98))] p-6 shadow-2xl shadow-black/25">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[#ffbb00]/70">
            {eyebrow}
          </p>
          {title || subtitle ? (
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {title ? <h2 className="text-3xl font-bold text-[#fff4cc]">{title}</h2> : null}
              {subtitle ? (
                <span className="text-base font-medium text-[#c9b27a] lg:text-lg">{subtitle}</span>
              ) : null}
            </div>
          ) : null}
          {description ? <p className="max-w-2xl text-sm leading-6 text-[#d4c39b]">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>

      {footer ? <div className="mt-6 border-t border-[rgba(255,187,0,0.1)] pt-5">{footer}</div> : null}
    </div>
  );
}

interface EventViewTabsProps {
  tabs: Array<{
    key: string;
    label: string;
    active: boolean;
    onClick: () => void;
  }>;
}

export function EventViewTabs({ tabs }: EventViewTabsProps) {
  return (
    <div className="inline-flex rounded-2xl border border-[rgba(255,187,0,0.12)] bg-black/30 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={tab.onClick}
          className={[
            'rounded-xl px-3 py-2 text-sm font-medium transition',
            tab.active
              ? 'bg-[#ffbb00]/14 text-[#fff1bf] shadow-[inset_0_0_0_1px_rgba(255,187,0,0.18)]'
              : 'text-slate-400 hover:text-slate-200',
          ].join(' ')}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

interface EventStatCardProps {
  label: string;
  value: ReactNode;
  supportingText?: string;
}

export function EventStatCard({ label, value, supportingText }: EventStatCardProps) {
  return (
    <Card variant="default">
      <CardBody className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.24em] text-[#a89465]">{label}</p>
        <div className="text-sm font-medium text-[#f5deb3]">{value}</div>
        {supportingText ? <p className="text-xs leading-5 text-[#a89465]">{supportingText}</p> : null}
      </CardBody>
    </Card>
  );
}
