/** Follow-up questions (form editor) modal for a ticket category. */

import { useMemo } from 'react';
import type { TicketCategory, TicketFormStep } from '../../api/endpoints';
import {
  Alert,
  Badge,
  Button,
  Card,
  Input,
  Modal,
  ModalFooter,
  Spinner,
} from '../../components/ui';
import {
  MAX_FORM_STEPS,
  MAX_QUESTIONS_PER_STEP,
  MAX_SELECT_OPTIONS,
  MAX_TOTAL_FOLLOW_UP_QUESTIONS,
  SELECT_CLASS,
} from './constants';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface FormEditorModalProps {
  open: boolean;
  category: TicketCategory | null;
  steps: TicketFormStep[];
  loading: boolean;
  saving: boolean;
  deleting: boolean;
  error: string | null;
  validationErrors: string[];
  onClose: () => void;
  onSave: () => void;
  onDelete: () => void;
  onStepsChange: React.Dispatch<React.SetStateAction<TicketFormStep[]>>;
  onError: (msg: string | null) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Immutably update a single step by index. */
function updateStep(
  setSteps: React.Dispatch<React.SetStateAction<TicketFormStep[]>>,
  index: number,
  updater: (step: TicketFormStep) => TicketFormStep,
) {
  setSteps((prev) => prev.map((s, i) => (i === index ? updater(s) : s)));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FormEditorModal({
  open,
  category,
  steps,
  loading,
  saving,
  deleting,
  error,
  validationErrors,
  onClose,
  onSave,
  onDelete,
  onStepsChange,
  onError,
}: FormEditorModalProps) {
  const totalQuestions = useMemo(
    () => steps.reduce((t, s) => t + s.questions.length, 0),
    [steps],
  );

  // --- Step management ---

  const addStep = () => {
    if (steps.length >= MAX_FORM_STEPS) {
      onError(`You can only configure up to ${MAX_FORM_STEPS} form steps.`);
      return;
    }
    onError(null);
    onStepsChange((prev) => [
      ...prev,
      {
        step_number: prev.length + 1,
        title: `Step ${prev.length + 1}`,
        questions: [],
        branch_rules: [],
        default_next_step: null,
      },
    ]);
  };

  const removeStep = (index: number) => {
    const removedStepNumber = index + 1;
    onStepsChange((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((step, i) => ({
          ...step,
          step_number: i + 1,
          default_next_step:
            step.default_next_step === removedStepNumber
              ? null
              : step.default_next_step && step.default_next_step > removedStepNumber
                ? step.default_next_step - 1
                : step.default_next_step,
          branch_rules: step.branch_rules.map((rule) => ({
            ...rule,
            next_step_number:
              rule.next_step_number === removedStepNumber
                ? null
                : rule.next_step_number && rule.next_step_number > removedStepNumber
                  ? rule.next_step_number - 1
                  : rule.next_step_number,
          })),
        })),
    );
  };

  // --- Question management ---

  const addQuestion = (stepIndex: number) => {
    onError(null);
    onStepsChange((prev) => {
      const total = prev.reduce((acc, s) => acc + s.questions.length, 0);
      if (total >= MAX_TOTAL_FOLLOW_UP_QUESTIONS) {
        onError(`You can only configure up to ${MAX_TOTAL_FOLLOW_UP_QUESTIONS} follow-up questions.`);
        return prev;
      }

      return prev.map((step, idx) => {
        if (idx !== stepIndex) return step;
        if (step.questions.length >= MAX_QUESTIONS_PER_STEP) {
          onError(`Each step can only contain up to ${MAX_QUESTIONS_PER_STEP} questions.`);
          return step;
        }
        const nextIndex = step.questions.length + 1;
        return {
          ...step,
          questions: [
            ...step.questions,
            {
              question_id: `q${step.step_number}_${nextIndex}`,
              label: '',
              input_type: 'text' as const,
              options: [],
              placeholder: '',
              style: 'short' as const,
              required: true,
              min_length: null,
              max_length: null,
              sort_order: nextIndex - 1,
            },
          ],
        };
      });
    });
  };

  const removeQuestion = (stepIndex: number, questionIndex: number) => {
    updateStep(onStepsChange, stepIndex, (step) => ({
      ...step,
      questions: step.questions
        .filter((_, i) => i !== questionIndex)
        .map((q, i) => ({ ...q, sort_order: i })),
    }));
  };

  // --- Select options ---

  const addSelectOption = (stepIndex: number, questionIndex: number) => {
    updateStep(onStepsChange, stepIndex, (step) => ({
      ...step,
      questions: step.questions.map((q, i) => {
        if (i !== questionIndex) return q;
        const current = q.options ?? [];
        if (current.length >= MAX_SELECT_OPTIONS) return q;
        return { ...q, options: [...current, { value: '', label: '' }] };
      }),
    }));
  };

  const updateSelectOption = (
    stepIndex: number,
    questionIndex: number,
    optionIndex: number,
    value: string,
  ) => {
    updateStep(onStepsChange, stepIndex, (step) => ({
      ...step,
      questions: step.questions.map((q, i) => {
        if (i !== questionIndex) return q;
        return {
          ...q,
          options: (q.options ?? []).map((opt, oi) =>
            oi === optionIndex ? { label: value, value } : opt,
          ),
        };
      }),
    }));
  };

  const removeSelectOption = (
    stepIndex: number,
    questionIndex: number,
    optionIndex: number,
  ) => {
    updateStep(onStepsChange, stepIndex, (step) => ({
      ...step,
      questions: step.questions.map((q, i) => {
        if (i !== questionIndex) return q;
        return { ...q, options: (q.options ?? []).filter((_, oi) => oi !== optionIndex) };
      }),
    }));
  };

  // --- Branch rules ---

  const addBranchRule = (stepIndex: number) => {
    updateStep(onStepsChange, stepIndex, (step) => ({
      ...step,
      branch_rules: [
        ...step.branch_rules,
        {
          question_id: step.questions[0]?.question_id ?? '',
          match_pattern: '',
          next_step_number: null,
        },
      ],
    }));
  };

  const removeBranchRule = (stepIndex: number, ruleIndex: number) => {
    updateStep(onStepsChange, stepIndex, (step) => ({
      ...step,
      branch_rules: step.branch_rules.filter((_, i) => i !== ruleIndex),
    }));
  };

  // --- Render ---

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={category ? `Follow-up Questions: ${category.name}` : 'Follow-up Questions'}
      size="lg"
      footer={
        <ModalFooter>
          <Button variant="secondary" onClick={onClose} disabled={saving || deleting}>
            Close
          </Button>
          <Button
            variant="danger"
            onClick={onDelete}
            loading={deleting}
            disabled={saving || loading || steps.length === 0}
          >
            {deleting ? 'Deleting…' : 'Delete Form'}
          </Button>
          <Button onClick={onSave} loading={saving} disabled={deleting || loading}>
            {saving ? 'Saving…' : 'Save Follow-up Questions'}
          </Button>
        </ModalFooter>
      }
    >
      {loading ? (
        <div className="flex items-center gap-3 py-4">
          <Spinner className="h-5 w-5" />
          <span className="text-gray-400">Loading follow-up questions…</span>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-400">
              Configure follow-up modal questions for this category. Max{' '}
              {MAX_TOTAL_FOLLOW_UP_QUESTIONS} questions total.
            </p>
            <Badge
              variant={
                totalQuestions > MAX_TOTAL_FOLLOW_UP_QUESTIONS
                  ? 'error'
                  : 'primary-outline'
              }
            >
              {totalQuestions}/{MAX_TOTAL_FOLLOW_UP_QUESTIONS}
            </Badge>
          </div>

          {error && <Alert variant="error">{error}</Alert>}

          {validationErrors.length > 0 && (
            <Alert variant="warning">
              <div className="space-y-1">
                <p className="font-medium">Validation warnings</p>
                {validationErrors.map((err, idx) => (
                  <p key={`${err}-${idx}`} className="text-xs">
                    • {err}
                  </p>
                ))}
              </div>
            </Alert>
          )}

          {steps.length === 0 ? (
            <Alert variant="info">
              No follow-up questions configured. Ticket creation will use the
              default description modal for this category.
            </Alert>
          ) : (
            <div className="space-y-3">
              {steps.map((step, stepIndex) => (
                <Card key={`step-${step.step_number}`} variant="ghost" padding="sm">
                  <div className="space-y-3">
                    {/* Step header */}
                    <div className="flex items-center justify-between gap-3">
                      <Input
                        label={`Step ${step.step_number} Title`}
                        value={step.title}
                        onChange={(e) =>
                          updateStep(onStepsChange, stepIndex, (cur) => ({
                            ...cur,
                            title: e.target.value,
                          }))
                        }
                        placeholder={`Step ${step.step_number}`}
                      />
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => removeStep(stepIndex)}
                        disabled={saving || deleting}
                      >
                        Remove Step
                      </Button>
                    </div>

                    {/* Questions */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-gray-300">Questions</p>
                        <Button
                          size="sm"
                          onClick={() => addQuestion(stepIndex)}
                          disabled={saving || deleting}
                        >
                          + Add Question
                        </Button>
                      </div>

                      {step.questions.length === 0 ? (
                        <p className="text-xs text-gray-500">
                          No questions in this step.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {step.questions.map((question, qIdx) => (
                            <QuestionCard
                              key={`${step.step_number}-q-${qIdx}`}
                              stepIndex={stepIndex}
                              questionIndex={qIdx}
                              question={question}
                              saving={saving}
                              deleting={deleting}
                              onChange={onStepsChange}
                              onAddOption={addSelectOption}
                              onUpdateOption={updateSelectOption}
                              onRemoveOption={removeSelectOption}
                              onRemove={removeQuestion}
                            />
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Branch Rules */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-gray-300">
                          Branch Rules
                        </p>
                        <Button
                          size="sm"
                          onClick={() => addBranchRule(stepIndex)}
                          disabled={
                            saving || deleting || step.questions.length === 0
                          }
                        >
                          + Add Rule
                        </Button>
                      </div>

                      {step.branch_rules.length === 0 ? (
                        <p className="text-xs text-gray-500">
                          No branch rules for this step.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {step.branch_rules.map((rule, rIdx) => (
                            <Card
                              key={`${step.step_number}-rule-${rIdx}`}
                              variant="default"
                              padding="sm"
                            >
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                <div>
                                  <label
                                    htmlFor={`rule-q-${stepIndex}-${rIdx}`}
                                    className="block text-sm font-medium text-gray-300 mb-1"
                                  >
                                    Question
                                  </label>
                                  <select
                                    id={`rule-q-${stepIndex}-${rIdx}`}
                                    value={rule.question_id}
                                    onChange={(e) =>
                                      updateStep(onStepsChange, stepIndex, (cur) => ({
                                        ...cur,
                                        branch_rules: cur.branch_rules.map((r, i) =>
                                          i === rIdx
                                            ? { ...r, question_id: e.target.value }
                                            : r,
                                        ),
                                      }))
                                    }
                                    className={SELECT_CLASS}
                                  >
                                    {step.questions.map((q, qi) => (
                                      <option
                                        key={q.question_id}
                                        value={q.question_id}
                                      >
                                        {q.label?.trim() || `Question ${qi + 1}`}
                                      </option>
                                    ))}
                                  </select>
                                </div>

                                <Input
                                  label="Regex Match"
                                  value={rule.match_pattern}
                                  onChange={(e) =>
                                    updateStep(onStepsChange, stepIndex, (cur) => ({
                                      ...cur,
                                      branch_rules: cur.branch_rules.map((r, i) =>
                                        i === rIdx
                                          ? { ...r, match_pattern: e.target.value }
                                          : r,
                                      ),
                                    }))
                                  }
                                  placeholder="(?i)billing"
                                />

                                <div>
                                  <label
                                    htmlFor={`rule-next-${stepIndex}-${rIdx}`}
                                    className="block text-sm font-medium text-gray-300 mb-1"
                                  >
                                    Next Step
                                  </label>
                                  <select
                                    id={`rule-next-${stepIndex}-${rIdx}`}
                                    value={rule.next_step_number ?? ''}
                                    onChange={(e) =>
                                      updateStep(onStepsChange, stepIndex, (cur) => ({
                                        ...cur,
                                        branch_rules: cur.branch_rules.map((r, i) =>
                                          i === rIdx
                                            ? {
                                                ...r,
                                                next_step_number: e.target.value
                                                  ? Number.parseInt(e.target.value, 10)
                                                  : null,
                                              }
                                            : r,
                                        ),
                                      }))
                                    }
                                    className={SELECT_CLASS}
                                  >
                                    <option value="">End Flow</option>
                                    {steps
                                      .filter((c) => c.step_number !== step.step_number)
                                      .map((c) => (
                                        <option
                                          key={`next-step-${c.step_number}`}
                                          value={c.step_number}
                                        >
                                          Step {c.step_number}
                                        </option>
                                      ))}
                                  </select>
                                </div>
                              </div>
                              <div className="flex justify-end mt-3">
                                <Button
                                  variant="danger"
                                  size="sm"
                                  onClick={() => removeBranchRule(stepIndex, rIdx)}
                                  disabled={saving || deleting}
                                >
                                  Remove Rule
                                </Button>
                              </div>
                            </Card>
                          ))}
                        </div>
                      )}

                      {/* Default next step */}
                      <div>
                        <label
                          htmlFor={`default-next-${stepIndex}`}
                          className="block text-sm font-medium text-gray-300 mb-1"
                        >
                          Default Next Step
                        </label>
                        <select
                          id={`default-next-${stepIndex}`}
                          value={step.default_next_step ?? ''}
                          onChange={(e) =>
                            updateStep(onStepsChange, stepIndex, (cur) => ({
                              ...cur,
                              default_next_step: e.target.value
                                ? Number.parseInt(e.target.value, 10)
                                : null,
                            }))
                          }
                          className={SELECT_CLASS}
                        >
                          <option value="">End Flow</option>
                          {steps
                            .filter((c) => c.step_number !== step.step_number)
                            .map((c) => (
                              <option
                                key={`default-next-${c.step_number}`}
                                value={c.step_number}
                              >
                                Step {c.step_number}
                              </option>
                            ))}
                        </select>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          <div className="pt-1">
            <Button onClick={addStep} disabled={saving || deleting}>
              + Add Step
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// QuestionCard – extracted to avoid deep nesting and enable reuse
// ---------------------------------------------------------------------------

interface QuestionCardProps {
  stepIndex: number;
  questionIndex: number;
  question: TicketFormStep['questions'][number];
  saving: boolean;
  deleting: boolean;
  onChange: React.Dispatch<React.SetStateAction<TicketFormStep[]>>;
  onAddOption: (stepIdx: number, qIdx: number) => void;
  onUpdateOption: (stepIdx: number, qIdx: number, optIdx: number, val: string) => void;
  onRemoveOption: (stepIdx: number, qIdx: number, optIdx: number) => void;
  onRemove: (stepIdx: number, qIdx: number) => void;
}

function QuestionCard({
  stepIndex,
  questionIndex,
  question,
  saving,
  deleting,
  onChange,
  onAddOption,
  onUpdateOption,
  onRemoveOption,
  onRemove,
}: QuestionCardProps) {
  return (
    <Card variant="default" padding="sm">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Input
          label="Question Label"
          value={question.label}
          onChange={(e) =>
            updateStep(onChange, stepIndex, (cur) => ({
              ...cur,
              questions: cur.questions.map((q, i) =>
                i === questionIndex ? { ...q, label: e.target.value } : q,
              ),
            }))
          }
          placeholder="What is the issue?"
        />
        <Input
          label="Placeholder"
          value={question.placeholder ?? ''}
          onChange={(e) =>
            updateStep(onChange, stepIndex, (cur) => ({
              ...cur,
              questions: cur.questions.map((q, i) =>
                i === questionIndex ? { ...q, placeholder: e.target.value } : q,
              ),
            }))
          }
          placeholder="Optional helper text"
        />
        <div>
          <label
            htmlFor={`q-type-${stepIndex}-${questionIndex}`}
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Question Type
          </label>
          <select
            id={`q-type-${stepIndex}-${questionIndex}`}
            value={question.input_type ?? 'text'}
            onChange={(e) =>
              updateStep(onChange, stepIndex, (cur) => ({
                ...cur,
                questions: cur.questions.map((q, i) =>
                  i === questionIndex
                    ? {
                        ...q,
                        input_type: e.target.value === 'select' ? ('select' as const) : ('text' as const),
                        options:
                          e.target.value === 'select'
                            ? q.options && q.options.length > 0
                              ? q.options
                              : [{ value: 'option_1', label: '' }]
                            : [],
                      }
                    : q,
                ),
              }))
            }
            className={SELECT_CLASS}
          >
            <option value="text">Text Input</option>
            <option value="select">Dropdown (Single Select)</option>
          </select>
        </div>
        <div>
          <label
            htmlFor={`q-style-${stepIndex}-${questionIndex}`}
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Style
          </label>
          <select
            id={`q-style-${stepIndex}-${questionIndex}`}
            value={question.style ?? 'short'}
            disabled={question.input_type === 'select'}
            onChange={(e) =>
              updateStep(onChange, stepIndex, (cur) => ({
                ...cur,
                questions: cur.questions.map((q, i) =>
                  i === questionIndex
                    ? {
                        ...q,
                        style: (e.target.value === 'paragraph' ? 'paragraph' : 'short') as
                          | 'short'
                          | 'paragraph',
                      }
                    : q,
                ),
              }))
            }
            className={SELECT_CLASS}
          >
            <option value="short">Short</option>
            <option value="paragraph">Paragraph</option>
          </select>
        </div>
      </div>

      {/* Select options */}
      {question.input_type === 'select' && (
        <div className="mt-3 space-y-2 rounded border border-slate-700 p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-300">
              Dropdown Options (max {MAX_SELECT_OPTIONS})
            </p>
            <Button
              size="sm"
              onClick={() => onAddOption(stepIndex, questionIndex)}
              disabled={(question.options?.length ?? 0) >= MAX_SELECT_OPTIONS}
            >
              + Add Option
            </Button>
          </div>
          {(question.options ?? []).length === 0 ? (
            <p className="text-xs text-gray-500">No options yet.</p>
          ) : (
            <div className="space-y-2">
              {(question.options ?? []).map((option, optIdx) => (
                <div
                  key={`${question.question_id}-opt-${optIdx}`}
                  className="flex items-end gap-2"
                >
                  <Input
                    className="flex-1"
                    label="Option Label"
                    value={option.label}
                    onChange={(e) =>
                      onUpdateOption(stepIndex, questionIndex, optIdx, e.target.value)
                    }
                    placeholder="Billing Support"
                  />
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => onRemoveOption(stepIndex, questionIndex, optIdx)}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end mt-3">
        <Button
          variant="danger"
          size="sm"
          onClick={() => onRemove(stepIndex, questionIndex)}
          disabled={saving || deleting}
        >
          Remove Question
        </Button>
      </div>
    </Card>
  );
}
