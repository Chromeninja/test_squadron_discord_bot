import { type ReactNode } from 'react';
import { BUILDER_STEPS, type BuilderStep } from './eventFlowShared';

interface StepProgressProps {
  builderStep: BuilderStep;
  stepIndex: number;
  onStepChange: (step: BuilderStep) => void;
}

export function StepProgress({ builderStep, stepIndex, onStepChange }: StepProgressProps) {
  return (
    <ol className="grid grid-cols-4 gap-3" role="list">
      {BUILDER_STEPS.map((step, index) => {
        const isActive = step.id === builderStep;
        const isComplete = index < stepIndex;

        return (
          <li key={step.id}>
            <button
              type="button"
              onClick={() => onStepChange(step.id)}
              className="group w-full text-left"
            >
              <span
                className={[
                  'block h-1 rounded-full transition-colors',
                  isActive || isComplete
                    ? 'bg-[#ffbb00]'
                    : 'bg-[#3a2a00] group-hover:bg-[#ffbb00]/35',
                ].join(' ')}
              />
              <span
                className={[
                  'mt-2 block text-sm transition-colors',
                  isActive ? 'text-[#fff1bf]' : isComplete ? 'text-[#ffdd73]' : 'text-[#a89465]',
                ].join(' ')}
              >
                {step.title}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
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
    <div className="space-y-4 rounded-xl border border-[#ffbb00]/15 bg-[#0f0b00]/55 p-5">
      <div>
        <p className="text-[11px] uppercase tracking-[0.24em] text-[#ffbb00]/70">{eyebrow}</p>
        <h4 className="mt-2 text-lg font-semibold text-[#fff4cc]">{title}</h4>
        <p className="mt-2 text-sm leading-6 text-[#d4c39b]">{description}</p>
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
    <div className="rounded-lg border border-[#ffbb00]/15 bg-[#120d00] p-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-[#ffbb00]/60">{label}</p>
      <p className="mt-2 text-sm leading-6 text-[#f5deb3]">{value}</p>
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
      <span className="text-[#a89465]">{label}</span>
      <span className={multiLine ? 'block text-[#f5deb3]' : 'text-right text-[#f5deb3]'}>{value}</span>
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
      : 'border-[#ffbb00]/18 bg-[#120d00] text-[#d4c39b] hover:border-[#ffbb00]/35 hover:bg-[#1a1304]',
  ].join(' ');
}
