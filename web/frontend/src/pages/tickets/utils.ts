/** Utility helpers shared across ticket sub-components. */

import type { TicketCategory, TicketFormStep } from '../../api/endpoints';

/** Format a UNIX timestamp (seconds) to locale string. */
export function formatTimestamp(ts: number | null): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

/** Resolve a category name by id, falling back to `#id` or `—`. */
export function getCategoryName(
  categoryId: number | null,
  categories: TicketCategory[],
): string {
  if (categoryId === null) return '—';
  const cat = categories.find((c) => c.id === categoryId);
  return cat ? cat.name : `#${categoryId}`;
}

/**
 * Normalise form steps before saving — fill defaults, re-index, and
 * enforce text-only questions so the backend receives valid data.
 */
export function normalizeStepsForSave(steps: TicketFormStep[]): TicketFormStep[] {
  return steps.map((step, stepIndex) => ({
    ...step,
    step_number: stepIndex + 1,
    title: step.title ?? '',
    questions: step.questions.map((q, questionIndex) => {
      const generatedQuestionId = `step${stepIndex + 1}_q${questionIndex + 1}`;
      return {
        ...q,
        question_id: q.question_id?.trim() || generatedQuestionId,
        label: q.label.trim(),
        input_type: 'text',
        options: [],
        placeholder: q.placeholder ?? '',
        style: q.style ?? 'short',
        required: q.required ?? true,
        min_length: q.min_length ?? null,
        max_length: q.max_length ?? null,
        sort_order: questionIndex,
      };
    }),
  }));
}
