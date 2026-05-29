import { type ReactNode } from 'react';
import { Card, CardBody } from '../components/ui';
import { BUILDER_STEPS, type BuilderStep } from './eventFlowShared';

interface StepNavigatorProps {
  builderStep: BuilderStep;
  stepIndex: number;
  onStepChange: (step: BuilderStep) => void;
}

export function StepNavigator({ builderStep, stepIndex, onStepChange }: StepNavigatorProps) {
  return (
    <Card variant="default">
      <CardBody className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">Steps</p>
        <ol className="grid gap-2 lg:grid-cols-1" role="list">
          {BUILDER_STEPS.map((step, index) => {
            const isActive = step.id === builderStep;
            const isComplete = index < stepIndex;

            return (
              <li key={step.id}>
                <button
                  type="button"
                  onClick={() => onStepChange(step.id)}
                  className={[
                    'flex w-full items-start gap-3 rounded-2xl border px-3 py-3 text-left transition',
                    isActive
                      ? 'border-[#ffbb00]/35 bg-[#ffbb00]/10'
                      : isComplete
                        ? 'border-emerald-500/30 bg-emerald-500/10'
                        : 'border-slate-800 bg-slate-900/80 hover:border-slate-700',
                  ].join(' ')}
                >
                  <div
                    className={[
                      'flex h-9 w-9 flex-none items-center justify-center rounded-full border text-sm font-semibold',
                      isActive
                        ? 'border-[#ffbb00]/45 bg-[#2b2006] text-[#fff1bf]'
                        : isComplete
                          ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200'
                          : 'border-slate-700 bg-slate-950 text-slate-300',
                    ].join(' ')}
                  >
                    {isComplete ? '✓' : index + 1}
                  </div>
                  <div>
                    <p className={isActive ? 'text-sm font-semibold text-white' : 'text-sm font-semibold text-slate-200'}>
                      {step.title}
                    </p>
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      </CardBody>
    </Card>
  );
}

interface EventSectionProps {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}

export function EventSection({ eyebrow, title, description, children }: EventSectionProps) {
  return (
    <div className="space-y-4 rounded-[24px] border border-[#ffbb00]/15 bg-[#0f0b00]/55 p-5">
      <div>
        <p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{eyebrow}</p>
        <h4 className="mt-2 text-lg font-semibold text-white">{title}</h4>
        <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

interface CompactSummaryCardProps {
  label: string;
  value: string;
}

export function CompactSummaryCard({ label, value }: CompactSummaryCardProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{label}</p>
      <p className="mt-2 text-sm leading-6 text-slate-100">{value}</p>
    </div>
  );
}

interface ReviewRowProps {
  label: string;
  value: string;
  multiLine?: boolean;
}

export function ReviewRow({ label, value, multiLine = false }: ReviewRowProps) {
  return (
    <div className={multiLine ? 'space-y-1' : 'flex items-start justify-between gap-4'}>
      <span className="text-slate-400">{label}</span>
      <span className={multiLine ? 'block text-slate-100' : 'text-right text-slate-100'}>{value}</span>
    </div>
  );
}

export function getOptionButtonClass(active: boolean, density: 'default' | 'compact' = 'default'): string {
  return [
    'rounded-full border transition',
    density === 'compact'
      ? 'px-3 py-2 text-xs font-medium'
      : 'px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em]',
    active
      ? 'border-[#ffbb00]/60 bg-[#2b2006] text-[#fff1bf]'
      : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-500',
  ].join(' ');
}
