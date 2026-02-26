/**
 * Ticket System management page.
 *
 * Provides full configuration for the thread-based ticketing system:
 * - Settings (channel, panel text, log channel, staff roles, messages)
 * - Category CRUD
 * - Ticket listing with pagination
 * - Live statistics
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  DiscordChannel,
  GuildRole,
  TicketCategory,
  TicketFormStep,
  TicketInfo,
  guildApi,
  ticketsApi,
} from '../api/endpoints';
import AccordionSection from '../components/AccordionSection';
import SearchableSelect, { type SelectOption } from '../components/SearchableSelect';
import SearchableMultiSelect, { type MultiSelectOption } from '../components/SearchableMultiSelect';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Spinner,
  Textarea,
} from '../components/ui';
import DiscordMarkdownEditor from '../components/DiscordMarkdownEditor';
import { handleApiError, showSuccess } from '../utils/toast';

interface TicketsProps {
  guildId: string;
}

const MAX_TOTAL_FOLLOW_UP_QUESTIONS = 10;
const MAX_QUESTIONS_PER_STEP = 5;
const MAX_FORM_STEPS = 10;
const MAX_SELECT_OPTIONS = 10;

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function Tickets({ guildId }: TicketsProps) {
  const isMountedRef = useRef(true);

  // --- Loading / error state ---
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- Discord data ---
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [roles, setRoles] = useState<GuildRole[]>([]);

  // --- Settings state ---
  const [channelId, setChannelId] = useState<string | null>(null);
  const [logChannelId, setLogChannelId] = useState<string | null>(null);
  const [panelTitle, setPanelTitle] = useState('');
  const [panelDescription, setPanelDescription] = useState('');
  const [closeMessage, setCloseMessage] = useState('');
  const [staffRoles, setStaffRoles] = useState<string[]>([]);
  const [defaultWelcomeMessage, setDefaultWelcomeMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [deploying, setDeploying] = useState(false);

  // --- Categories state ---
  const [categories, setCategories] = useState<TicketCategory[]>([]);
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<TicketCategory | null>(null);
  const [deletingCategory, setDeletingCategory] = useState<TicketCategory | null>(null);
  const [catName, setCatName] = useState('');
  const [catDescription, setCatDescription] = useState('');
  const [catEmoji, setCatEmoji] = useState('');
  const [catWelcomeMessage, setCatWelcomeMessage] = useState('');
  const [catRoleIds, setCatRoleIds] = useState<string[]>([]);
  const [catSaving, setCatSaving] = useState(false);
  const [catDeleting, setCatDeleting] = useState(false);

  // --- Follow-up form editor state ---
  const [formEditorOpen, setFormEditorOpen] = useState(false);
  const [formCategory, setFormCategory] = useState<TicketCategory | null>(null);
  const [formSteps, setFormSteps] = useState<TicketFormStep[]>([]);
  const [formLoading, setFormLoading] = useState(false);
  const [formSaving, setFormSaving] = useState(false);
  const [formDeleting, setFormDeleting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formValidationErrors, setFormValidationErrors] = useState<string[]>([]);

  // --- Tickets list state ---
  const [tickets, setTickets] = useState<TicketInfo[]>([]);
  const [ticketFilter, setTicketFilter] = useState<string>('');
  const [ticketPage, setTicketPage] = useState(1);
  const [ticketTotal, setTicketTotal] = useState(0);
  const ticketPageSize = 20;

  // --- Stats state ---
  const [statsOpen, setStatsOpen] = useState(0);
  const [statsClosed, setStatsClosed] = useState(0);
  const [statsTotal, setStatsTotal] = useState(0);

  // --- Derived data ---
  const channelOptions: SelectOption[] = useMemo(
    () =>
      channels.map((c) => ({
        id: c.id,
        name: c.name,
        category: c.category ?? undefined,
      })),
    [channels]
  );

  const roleOptions: MultiSelectOption[] = useMemo(
    () => roles.map((r) => ({ id: r.id, name: r.name })),
    [roles]
  );

  // --- Fetch all data ---
  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [settingsRes, catsRes, statsRes, channelsRes, rolesRes] = await Promise.all([
        ticketsApi.getSettings(),
        ticketsApi.getCategories(),
        ticketsApi.getStats(),
        guildApi.getDiscordChannels(guildId),
        guildApi.getDiscordRoles(guildId),
      ]);

      if (!isMountedRef.current) return;

      // Settings
      const s = settingsRes.settings;
      setChannelId(s.channel_id);
      setLogChannelId(s.log_channel_id);
      setPanelTitle(s.panel_title ?? '');
      setPanelDescription(s.panel_description ?? '');
      setCloseMessage(s.close_message ?? '');
      setStaffRoles(s.staff_roles);
      setDefaultWelcomeMessage(s.default_welcome_message ?? '');

      // Categories
      setCategories(catsRes.categories);

      // Stats
      setStatsOpen(statsRes.open);
      setStatsClosed(statsRes.closed);
      setStatsTotal(statsRes.total);

      // Discord data
      setChannels(channelsRes.channels);
      setRoles(rolesRes.roles);
    } catch (err) {
      if (isMountedRef.current) {
        setError('Failed to load ticket settings.');
        handleApiError(err, 'Failed to load ticket settings');
      }
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [guildId]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchAll();
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchAll]);

  // --- Fetch tickets list ---
  const fetchTickets = useCallback(async () => {
    try {
      const res = await ticketsApi.listTickets(
        ticketFilter || undefined,
        ticketPage,
        ticketPageSize
      );
      if (isMountedRef.current) {
        setTickets(res.items);
        setTicketTotal(res.total);
      }
    } catch (err) {
      handleApiError(err, 'Failed to load tickets');
    }
  }, [ticketFilter, ticketPage]);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  // --- Handlers ---
  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      await ticketsApi.updateSettings({
        channel_id: channelId,
        panel_title: panelTitle || null,
        panel_description: panelDescription || null,
        log_channel_id: logChannelId,
        close_message: closeMessage || null,
        staff_roles: staffRoles,
        default_welcome_message: defaultWelcomeMessage || null,
      });
      showSuccess('Ticket settings saved');
    } catch (err) {
      handleApiError(err, 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleDeployPanel = async () => {
    setDeploying(true);
    try {
      await ticketsApi.deployPanel();
      showSuccess('Ticket panel deployed!');
    } catch (err) {
      handleApiError(err, 'Failed to deploy panel');
    } finally {
      setDeploying(false);
    }
  };

  // --- Category modal ---
  const openCreateCategory = () => {
    setEditingCategory(null);
    setCatName('');
    setCatDescription('');
    setCatEmoji('');
    setCatWelcomeMessage('');
    setCatRoleIds([]);
    setCategoryModalOpen(true);
  };

  const openEditCategory = (cat: TicketCategory) => {
    setEditingCategory(cat);
    setCatName(cat.name);
    setCatDescription(cat.description);
    setCatEmoji(cat.emoji ?? '');
    setCatWelcomeMessage(cat.welcome_message);
    setCatRoleIds(cat.role_ids);
    setCategoryModalOpen(true);
  };

  const handleSaveCategory = async () => {
    setCatSaving(true);
    try {
      if (editingCategory) {
        await ticketsApi.updateCategory(editingCategory.id, {
          name: catName,
          description: catDescription,
          welcome_message: catWelcomeMessage,
          emoji: catEmoji || null,
          role_ids: catRoleIds,
        });
        showSuccess('Category updated');
      } else {
        await ticketsApi.createCategory({
          guild_id: guildId,
          name: catName,
          description: catDescription,
          welcome_message: catWelcomeMessage,
          emoji: catEmoji || null,
          role_ids: catRoleIds,
        });
        showSuccess('Category created');
      }
      setCategoryModalOpen(false);
      // Refresh categories
      const res = await ticketsApi.getCategories();
      if (isMountedRef.current) setCategories(res.categories);
    } catch (err) {
      handleApiError(err, 'Failed to save category');
    } finally {
      setCatSaving(false);
    }
  };

  const handleDeleteCategory = async () => {
    if (!deletingCategory) return;
    setCatDeleting(true);
    try {
      await ticketsApi.deleteCategory(deletingCategory.id);
      showSuccess('Category deleted');
      setDeletingCategory(null);
      const res = await ticketsApi.getCategories();
      if (isMountedRef.current) setCategories(res.categories);
    } catch (err) {
      handleApiError(err, 'Failed to delete category');
    } finally {
      setCatDeleting(false);
    }
  };

  const totalFollowUpQuestions = useMemo(
    () => formSteps.reduce((total, step) => total + step.questions.length, 0),
    [formSteps]
  );

  const normalizeStepsForSave = (steps: TicketFormStep[]): TicketFormStep[] =>
    steps.map((step, stepIndex) => ({
      ...step,
      step_number: stepIndex + 1,
      title: step.title ?? '',
      questions: step.questions.map((q, questionIndex) => {
        const generatedQuestionId = `step${stepIndex + 1}_q${questionIndex + 1}`;
        return {
          ...q,
          question_id: q.question_id?.trim() || generatedQuestionId,
          label: q.label.trim(),
          input_type: q.input_type === 'select' ? 'select' : 'text',
          options:
            q.input_type === 'select'
              ? (q.options ?? [])
                  .map((option) => {
                    const label = option.label.trim();
                    return {
                      value: label,
                      label,
                    };
                  })
                  .filter((option) => option.label)
              : [],
          placeholder: q.placeholder ?? '',
          style: q.style ?? 'short',
          required: q.required ?? true,
          min_length: q.min_length ?? null,
          max_length: q.max_length ?? null,
          sort_order: questionIndex,
        };
      }),
      branch_rules: step.branch_rules.map((rule) => {
        const fallbackQuestionId =
          step.questions[0]?.question_id?.trim() || `step${stepIndex + 1}_q1`;
        return {
          question_id: rule.question_id || fallbackQuestionId,
          match_pattern: rule.match_pattern,
          next_step_number: rule.next_step_number,
        };
      }),
      default_next_step: step.default_next_step,
    }));

  const openFollowUpEditor = async (category: TicketCategory) => {
    setFormCategory(category);
    setFormEditorOpen(true);
    setFormLoading(true);
    setFormError(null);
    setFormValidationErrors([]);

    try {
      const res = await ticketsApi.getCategoryForm(category.id);
      const sorted = [...(res.config?.steps ?? [])].sort(
        (a, b) => a.step_number - b.step_number
      );
      setFormSteps(
        sorted.map((step) => ({
          ...step,
          questions: step.questions.map((question) => ({
            ...question,
            options: (question.options ?? []).map((option) => {
              const label = option.label?.trim() || option.value?.trim() || '';
              return { label, value: label };
            }),
          })),
        }))
      );
    } catch (err) {
      setFormError('Failed to load follow-up questions for this category.');
      handleApiError(err, 'Failed to load follow-up questions');
    } finally {
      setFormLoading(false);
    }
  };

  const closeFollowUpEditor = () => {
    setFormEditorOpen(false);
    setFormCategory(null);
    setFormSteps([]);
    setFormError(null);
    setFormValidationErrors([]);
  };

  const addStep = () => {
    if (formSteps.length >= 10) {
      setFormError('You can only configure up to 10 form steps.');
      return;
    }
    setFormError(null);
    setFormSteps((prev) => [
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
    setFormSteps((prev) =>
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
        }))
    );
  };

  const updateStep = (index: number, updater: (step: TicketFormStep) => TicketFormStep) => {
    setFormSteps((prev) => prev.map((step, i) => (i === index ? updater(step) : step)));
  };

  const addQuestion = (stepIndex: number) => {
    setFormError(null);
    setFormSteps((prev) => {
      const total = prev.reduce((acc, step) => acc + step.questions.length, 0);
      if (total >= MAX_TOTAL_FOLLOW_UP_QUESTIONS) {
        setFormError(`You can only configure up to ${MAX_TOTAL_FOLLOW_UP_QUESTIONS} follow-up questions.`);
        return prev;
      }

      return prev.map((step, idx) => {
        if (idx !== stepIndex) return step;
        if (step.questions.length >= MAX_QUESTIONS_PER_STEP) {
          setFormError(`Each step can only contain up to ${MAX_QUESTIONS_PER_STEP} questions.`);
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
              input_type: 'text',
              options: [],
              placeholder: '',
              style: 'short',
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
    updateStep(stepIndex, (step) => ({
      ...step,
      questions: step.questions
        .filter((_, i) => i !== questionIndex)
        .map((q, i) => ({ ...q, sort_order: i })),
    }));
  };

  const addSelectOption = (stepIndex: number, questionIndex: number) => {
    updateStep(stepIndex, (step) => ({
      ...step,
      questions: step.questions.map((q, i) => {
        if (i !== questionIndex) return q;
        const currentOptions = q.options ?? [];
        if (currentOptions.length >= 10) return q;
        return {
          ...q,
          options: [
            ...currentOptions,
            {
              value: '',
              label: '',
            },
          ],
        };
      }),
    }));
  };

  const updateSelectOption = (
    stepIndex: number,
    questionIndex: number,
    optionIndex: number,
    value: string
  ) => {
    const label = value;
    updateStep(stepIndex, (step) => ({
      ...step,
      questions: step.questions.map((q, i) => {
        if (i !== questionIndex) return q;
        return {
          ...q,
          options: (q.options ?? []).map((option, optionPos) =>
            optionPos === optionIndex
              ? { ...option, label, value: label }
              : option
          ),
        };
      }),
    }));
  };

  const removeSelectOption = (
    stepIndex: number,
    questionIndex: number,
    optionIndex: number
  ) => {
    updateStep(stepIndex, (step) => ({
      ...step,
      questions: step.questions.map((q, i) => {
        if (i !== questionIndex) return q;
        return {
          ...q,
          options: (q.options ?? []).filter((_, idx) => idx !== optionIndex),
        };
      }),
    }));
  };

  const addBranchRule = (stepIndex: number) => {
    updateStep(stepIndex, (step) => ({
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
    updateStep(stepIndex, (step) => ({
      ...step,
      branch_rules: step.branch_rules.filter((_, i) => i !== ruleIndex),
    }));
  };

  const runFormValidation = async (categoryId: number) => {
    try {
      const validation = await ticketsApi.validateCategoryForm(categoryId);
      setFormValidationErrors(validation.errors ?? []);
      return validation.valid;
    } catch (err) {
      handleApiError(err, 'Failed to validate follow-up questions');
      return false;
    }
  };

  const handleSaveFollowUpForm = async () => {
    if (!formCategory) return;

    setFormError(null);
    setFormValidationErrors([]);
    const normalized = normalizeStepsForSave(formSteps);
    const total = normalized.reduce((acc, step) => acc + step.questions.length, 0);

    const validationErrors: string[] = [];

    if (normalized.length > MAX_FORM_STEPS) {
      validationErrors.push(
        `This category has ${normalized.length} steps. Maximum allowed is ${MAX_FORM_STEPS}.`
      );
    }

    if (total > MAX_TOTAL_FOLLOW_UP_QUESTIONS) {
      validationErrors.push(
        `This category has ${total} questions. Maximum allowed is ${MAX_TOTAL_FOLLOW_UP_QUESTIONS}.`
      );
    }

    const stepNumbers = new Set<number>();
    for (const step of normalized) {
      if (stepNumbers.has(step.step_number)) {
        validationErrors.push(`Duplicate step number ${step.step_number}.`);
      }
      stepNumbers.add(step.step_number);
    }

    for (const step of normalized) {
      const stepLabel = `Step ${step.step_number}`;

      if (step.questions.length > MAX_QUESTIONS_PER_STEP) {
        validationErrors.push(
          `${stepLabel} has ${step.questions.length} questions. Maximum allowed is ${MAX_QUESTIONS_PER_STEP}.`
        );
      }

      const questionIds = new Set<string>();
      let selectQuestions = 0;

      for (const question of step.questions) {
        const questionId = question.question_id.trim();
        const questionLabel = question.label.trim();

        if (!questionLabel) {
          validationErrors.push('Every follow-up question requires a label.');
        }

        if (!questionId) {
          validationErrors.push(`${stepLabel} has a question with an empty question ID.`);
        } else {
          if (questionIds.has(questionId)) {
            validationErrors.push(
              `${stepLabel} has duplicate question ID \"${questionId}\".`
            );
          }
          questionIds.add(questionId);
        }

        if (question.input_type === 'select') {
          selectQuestions += 1;
          const options = question.options ?? [];
          if (options.length < 1 || options.length > MAX_SELECT_OPTIONS) {
            validationErrors.push(
              `${stepLabel} dropdown questions require 1-${MAX_SELECT_OPTIONS} options.`
            );
          }

          const optionValues = new Set<string>();
          for (const option of options) {
            const optionValue = option.value.trim();
            const optionLabel = option.label.trim();
            if (!optionValue || !optionLabel) {
              validationErrors.push(
                `${stepLabel} has a dropdown option with an empty label.`
              );
              continue;
            }
            if (optionValues.has(optionValue)) {
              validationErrors.push(
                `${stepLabel} has duplicate dropdown option labels.`
              );
              continue;
            }
            optionValues.add(optionValue);
          }
        }
      }

      if (selectQuestions > 1) {
        validationErrors.push(`${stepLabel} can only contain one dropdown question.`);
      }

      if (selectQuestions === 1 && step.questions.length > 1) {
        validationErrors.push(
          `${stepLabel} cannot mix dropdown questions with other question types.`
        );
      }

      for (const rule of step.branch_rules) {
        const ruleQuestionId = rule.question_id.trim();
        if (!ruleQuestionId) {
          validationErrors.push(`${stepLabel} has a branch rule with an empty question ID.`);
        } else if (!questionIds.has(ruleQuestionId)) {
          validationErrors.push(
            `${stepLabel} has a branch rule referencing unknown question ID \"${ruleQuestionId}\".`
          );
        }

        if (rule.match_pattern) {
          try {
            new RegExp(rule.match_pattern);
          } catch {
            validationErrors.push(
              `${stepLabel} has an invalid regex pattern: ${rule.match_pattern}`
            );
          }
        }

        if (
          rule.next_step_number !== null &&
          !stepNumbers.has(rule.next_step_number)
        ) {
          validationErrors.push(
            `${stepLabel} has a branch rule pointing to missing step ${rule.next_step_number}.`
          );
        }
      }

      if (
        step.default_next_step !== null &&
        !stepNumbers.has(step.default_next_step)
      ) {
        validationErrors.push(
          `${stepLabel} has a default next step pointing to missing step ${step.default_next_step}.`
        );
      }
    }

    if (validationErrors.length > 0) {
      setFormError(validationErrors[0]);
      setFormValidationErrors(validationErrors);
      return;
    }

    setFormSaving(true);
    try {
      await ticketsApi.updateCategoryForm(formCategory.id, { steps: normalized });
      const isValid = await runFormValidation(formCategory.id);
      showSuccess(
        isValid
          ? 'Follow-up questions saved'
          : 'Follow-up questions saved with validation warnings'
      );
    } catch (err) {
      const detail = (
        err as {
          response?: {
            data?: {
              detail?: { errors?: string[]; message?: string } | string;
            };
          };
        }
      )?.response?.data?.detail;
      const apiErrors =
        typeof detail === 'object' && detail !== null && Array.isArray(detail.errors)
          ? detail.errors
          : [];
      const apiMessage =
        typeof detail === 'string'
          ? detail
          : typeof detail === 'object' && detail !== null && typeof detail.message === 'string'
            ? detail.message
            : null;

      if (Array.isArray(apiErrors) && apiErrors.length > 0) {
        setFormError(apiErrors[0]);
        setFormValidationErrors(apiErrors);
      } else if (apiMessage) {
        setFormError(apiMessage);
        setFormValidationErrors([]);
      } else {
        setFormValidationErrors([]);
        handleApiError(err, 'Failed to save follow-up questions');
      }
    } finally {
      setFormSaving(false);
    }
  };

  const handleDeleteFollowUpForm = async () => {
    if (!formCategory) return;
    setFormDeleting(true);
    setFormError(null);
    try {
      await ticketsApi.deleteCategoryForm(formCategory.id);
      setFormSteps([]);
      setFormValidationErrors([]);
      showSuccess('Follow-up questions removed for this category');
    } catch (err) {
      handleApiError(err, 'Failed to delete follow-up questions');
    } finally {
      setFormDeleting(false);
    }
  };

  const ticketTotalPages = Math.ceil(ticketTotal / ticketPageSize) || 1;

  const getCategoryName = (categoryId: number | null): string => {
    if (categoryId === null) return '—';
    const cat = categories.find((c) => c.id === categoryId);
    return cat ? cat.name : `#${categoryId}`;
  };

  const formatTimestamp = (ts: number | null): string => {
    if (!ts) return '—';
    return new Date(ts * 1000).toLocaleString();
  };

  // --- Loading skeleton ---
  if (loading) {
    return (
      <Card variant="default" className="animate-pulse">
        <CardBody>
          <div className="flex items-center gap-3">
            <Spinner className="h-5 w-5" />
            <span className="text-gray-400">Loading ticket settings…</span>
          </div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return <Alert variant="error">{error}</Alert>;
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">🎫 Ticket System</h2>

      {/* ---------------------------------------------------------------- */}
      {/* Statistics */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card variant="default">
          <CardBody className="text-center">
            <p className="text-3xl font-bold text-blue-400">{statsOpen}</p>
            <p className="text-sm text-gray-400 mt-1">Open Tickets</p>
          </CardBody>
        </Card>
        <Card variant="default">
          <CardBody className="text-center">
            <p className="text-3xl font-bold text-green-400">{statsClosed}</p>
            <p className="text-sm text-gray-400 mt-1">Closed Tickets</p>
          </CardBody>
        </Card>
        <Card variant="default">
          <CardBody className="text-center">
            <p className="text-3xl font-bold text-gray-300">{statsTotal}</p>
            <p className="text-sm text-gray-400 mt-1">Total Tickets</p>
          </CardBody>
        </Card>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Settings */}
      {/* ---------------------------------------------------------------- */}
      <AccordionSection title="Settings" defaultOpen>
        <div className="space-y-6">
          {/* Ticket Channel */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Ticket Channel</h5>
            <p className="text-xs text-gray-500 mb-2">
              The text channel where the ticket panel embed will be posted.
            </p>
            <SearchableSelect
              options={channelOptions}
              selected={channelId}
              onChange={setChannelId}
              placeholder="Select a channel…"
            />
          </div>

          {/* Log Channel */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Log Channel</h5>
            <p className="text-xs text-gray-500 mb-2">
              Channel where ticket open/close events are logged. Optional.
            </p>
            <SearchableSelect
              options={channelOptions}
              selected={logChannelId}
              onChange={setLogChannelId}
              placeholder="Select a log channel…"
            />
          </div>

          {/* Staff Roles */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Staff Roles</h5>
            <p className="text-xs text-gray-500 mb-2">
              Roles that can view and close all tickets. Members with these roles are
              auto-mentioned in new ticket threads.
            </p>
            <SearchableMultiSelect
              options={roleOptions}
              selected={staffRoles}
              onChange={setStaffRoles}
              placeholder="Search roles…"
              componentId="ticket-staff-roles"
            />
          </div>

          {/* Panel Title */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Panel Title</h5>
            <p className="text-xs text-gray-500 mb-2">
              Title of the ticket panel embed. Leave empty for the default.
            </p>
            <Input
              value={panelTitle}
              onChange={(e) => setPanelTitle(e.target.value)}
              placeholder="🎫 Support Tickets"
            />
          </div>

          {/* Panel Description */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Panel Description</h5>
            <p className="text-xs text-gray-500 mb-2">
              Description shown on the ticket panel embed.
            </p>
            <DiscordMarkdownEditor
              value={panelDescription}
              onChange={setPanelDescription}
              placeholder="Click the button below to create a support ticket."
              rows={3}
              helperText="Use Discord markdown for clean panel copy (bold, italics, bullets, quotes, code, and links)."
            />
          </div>

          {/* Close Message */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Close Message</h5>
            <p className="text-xs text-gray-500 mb-2">
              Message displayed when a ticket is closed.
            </p>
            <DiscordMarkdownEditor
              value={closeMessage}
              onChange={setCloseMessage}
              placeholder="This ticket has been closed."
              rows={2}
              helperText="Supports Discord formatting and list/quote patterns for clear closure guidance."
            />
          </div>

          {/* Default Welcome Message */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Default Welcome Message</h5>
            <p className="text-xs text-gray-500 mb-2">
              Welcome message for new tickets without a category-specific message.
            </p>
            <DiscordMarkdownEditor
              value={defaultWelcomeMessage}
              onChange={setDefaultWelcomeMessage}
              placeholder="Welcome to your support ticket! Please describe your issue…"
              rows={3}
              helperText="Use concise Discord markdown prompts to improve intake quality."
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3 pt-2">
            <Button onClick={handleSaveSettings} loading={saving}>
              {saving ? 'Saving…' : 'Save Settings'}
            </Button>
            <Button
              variant="success"
              onClick={handleDeployPanel}
              loading={deploying}
              disabled={!channelId}
            >
              {deploying ? 'Deploying…' : '🚀 Deploy Panel'}
            </Button>
            {!channelId && (
              <span className="text-xs text-gray-500">
                Select a ticket channel before deploying the panel.
              </span>
            )}
          </div>
        </div>
      </AccordionSection>

      {/* ---------------------------------------------------------------- */}
      {/* Categories */}
      {/* ---------------------------------------------------------------- */}
      <AccordionSection title="Categories">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">
              Ticket categories let users choose a topic when creating a ticket.
              Each category can have its own welcome message and notified roles.
            </p>
            <Button size="sm" onClick={openCreateCategory} className="flex-shrink-0 ml-4">
              + Add Category
            </Button>
          </div>

          {categories.length === 0 ? (
            <Alert variant="info">
              No categories configured. Tickets will be created without a category.
            </Alert>
          ) : (
            <div className="space-y-2">
              {categories.map((cat) => (
                <Card key={cat.id} variant="ghost" padding="sm">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {cat.emoji && <span className="text-lg">{cat.emoji}</span>}
                      <div>
                        <p className="font-medium text-white">{cat.name}</p>
                        {cat.description && (
                          <p className="text-xs text-gray-400">{cat.description}</p>
                        )}
                      </div>
                      {cat.role_ids.length > 0 && (
                        <Badge variant="primary-outline" className="ml-2">
                          {cat.role_ids.length} role{cat.role_ids.length !== 1 ? 's' : ''}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openFollowUpEditor(cat)}
                      >
                        Follow-up Questions
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEditCategory(cat)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => setDeletingCategory(cat)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </AccordionSection>

      {/* ---------------------------------------------------------------- */}
      {/* Ticket List */}
      {/* ---------------------------------------------------------------- */}
      <AccordionSection title="Tickets">
        <div className="space-y-4">
          {/* Filter */}
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-400">Filter:</label>
            <select
              value={ticketFilter}
              onChange={(e) => {
                setTicketFilter(e.target.value);
                setTicketPage(1);
              }}
              className="bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </div>

          {/* Table */}
          {tickets.length === 0 ? (
            <Alert variant="info">No tickets found.</Alert>
          ) : (
            <div className="bg-slate-800/50 rounded border border-slate-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-800/80 text-xs text-gray-400">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">ID</th>
                    <th className="text-left px-3 py-2 font-medium">Creator</th>
                    <th className="text-left px-3 py-2 font-medium">Category</th>
                    <th className="text-left px-3 py-2 font-medium">Status</th>
                    <th className="text-left px-3 py-2 font-medium">Created</th>
                    <th className="text-left px-3 py-2 font-medium">Closed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {tickets.map((t) => (
                    <tr
                      key={t.id}
                      className="hover:bg-slate-700/30 transition-colors"
                    >
                      <td className="px-3 py-2 font-mono text-xs">{t.id}</td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-300">
                        {t.user_id}
                      </td>
                      <td className="px-3 py-2">{getCategoryName(t.category_id)}</td>
                      <td className="px-3 py-2">
                        <Badge variant={t.status === 'open' ? 'success' : 'neutral'}>
                          {t.status}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">
                        {formatTimestamp(t.created_at)}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">
                        {formatTimestamp(t.closed_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {ticketTotal > ticketPageSize && (
            <Pagination
              page={ticketPage}
              totalPages={ticketTotalPages}
              onPrevious={() => setTicketPage((p) => Math.max(1, p - 1))}
              onNext={() => setTicketPage((p) => Math.min(ticketTotalPages, p + 1))}
              summary={`${ticketTotal} ticket${ticketTotal !== 1 ? 's' : ''}`}
            />
          )}
        </div>
      </AccordionSection>

      {/* ---------------------------------------------------------------- */}
      {/* Category Create/Edit Modal */}
      {/* ---------------------------------------------------------------- */}
      <Modal
        open={categoryModalOpen}
        onClose={() => setCategoryModalOpen(false)}
        title={editingCategory ? 'Edit Category' : 'New Category'}
        size="md"
        footer={
          <ModalFooter>
            <Button
              variant="secondary"
              onClick={() => setCategoryModalOpen(false)}
              disabled={catSaving}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveCategory}
              loading={catSaving}
              disabled={!catName.trim()}
            >
              {catSaving ? 'Saving…' : editingCategory ? 'Update' : 'Create'}
            </Button>
          </ModalFooter>
        }
      >
        <div className="space-y-4">
          <Input
            label="Name"
            value={catName}
            onChange={(e) => setCatName(e.target.value)}
            placeholder="e.g. General Support"
          />
          <Input
            label="Emoji"
            value={catEmoji}
            onChange={(e) => setCatEmoji(e.target.value)}
            placeholder="e.g. 📩"
            helperText="Single emoji shown in the dropdown."
          />
          <Textarea
            label="Description"
            value={catDescription}
            onChange={(e) => setCatDescription(e.target.value)}
            placeholder="Brief description shown in the category dropdown."
            rows={2}
          />
          <DiscordMarkdownEditor
            label="Welcome Message"
            value={catWelcomeMessage}
            onChange={setCatWelcomeMessage}
            placeholder="Custom welcome message for tickets in this category. Leave empty to use the default."
            rows={3}
            helperText="Category welcome messages support Discord markdown (bold, bullets, italics, quotes, code, links)."
          />
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Notified Roles</h5>
            <p className="text-xs text-gray-500 mb-2">
              Roles mentioned in ticket threads for this category. Overrides the
              global staff roles if set.
            </p>
            <SearchableMultiSelect
              options={roleOptions}
              selected={catRoleIds}
              onChange={setCatRoleIds}
              placeholder="Search roles…"
              componentId="cat-role-ids"
            />
          </div>
        </div>
      </Modal>

      {/* ---------------------------------------------------------------- */}
      {/* Category Follow-up Questions */}
      {/* ---------------------------------------------------------------- */}
      <Modal
        open={formEditorOpen}
        onClose={closeFollowUpEditor}
        title={formCategory ? `Follow-up Questions: ${formCategory.name}` : 'Follow-up Questions'}
        size="lg"
        footer={
          <ModalFooter>
            <Button variant="secondary" onClick={closeFollowUpEditor} disabled={formSaving || formDeleting}>
              Close
            </Button>
            <Button
              variant="danger"
              onClick={handleDeleteFollowUpForm}
              loading={formDeleting}
              disabled={formSaving || formLoading || formSteps.length === 0}
            >
              {formDeleting ? 'Deleting…' : 'Delete Form'}
            </Button>
            <Button onClick={handleSaveFollowUpForm} loading={formSaving} disabled={formDeleting || formLoading}>
              {formSaving ? 'Saving…' : 'Save Follow-up Questions'}
            </Button>
          </ModalFooter>
        }
      >
        {formLoading ? (
          <div className="flex items-center gap-3 py-4">
            <Spinner className="h-5 w-5" />
            <span className="text-gray-400">Loading follow-up questions…</span>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-gray-400">
                Configure follow-up modal questions for this category. Max {MAX_TOTAL_FOLLOW_UP_QUESTIONS} questions total.
              </p>
              <Badge variant={totalFollowUpQuestions > MAX_TOTAL_FOLLOW_UP_QUESTIONS ? 'error' : 'primary-outline'}>
                {totalFollowUpQuestions}/{MAX_TOTAL_FOLLOW_UP_QUESTIONS}
              </Badge>
            </div>

            {formError && <Alert variant="error">{formError}</Alert>}

            {formValidationErrors.length > 0 && (
              <Alert variant="warning">
                <div className="space-y-1">
                  <p className="font-medium">Validation warnings</p>
                  {formValidationErrors.map((error, index) => (
                    <p key={`${error}-${index}`} className="text-xs">
                      • {error}
                    </p>
                  ))}
                </div>
              </Alert>
            )}

            {formSteps.length === 0 ? (
              <Alert variant="info">
                No follow-up questions configured. Ticket creation will use the default description modal for this category.
              </Alert>
            ) : (
              <div className="space-y-3">
                {formSteps.map((step, stepIndex) => (
                  <Card key={`step-${step.step_number}`} variant="ghost" padding="sm">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <Input
                          label={`Step ${step.step_number} Title`}
                          value={step.title}
                          onChange={(e) =>
                            updateStep(stepIndex, (current) => ({
                              ...current,
                              title: e.target.value,
                            }))
                          }
                          placeholder={`Step ${step.step_number}`}
                        />
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => removeStep(stepIndex)}
                          disabled={formSaving || formDeleting}
                        >
                          Remove Step
                        </Button>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-gray-300">Questions</p>
                          <Button
                            size="sm"
                            onClick={() => addQuestion(stepIndex)}
                            disabled={formSaving || formDeleting}
                          >
                            + Add Question
                          </Button>
                        </div>

                        {step.questions.length === 0 ? (
                          <p className="text-xs text-gray-500">No questions in this step.</p>
                        ) : (
                          <div className="space-y-2">
                            {step.questions.map((question, questionIndex) => (
                              <Card
                                key={`${step.step_number}-question-${questionIndex}`}
                                variant="default"
                                padding="sm"
                              >
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                  <Input
                                    label="Question Label"
                                    value={question.label}
                                    onChange={(e) =>
                                      updateStep(stepIndex, (current) => ({
                                        ...current,
                                        questions: current.questions.map((q, i) =>
                                          i === questionIndex ? { ...q, label: e.target.value } : q
                                        ),
                                      }))
                                    }
                                    placeholder="What is the issue?"
                                  />
                                  <Input
                                    label="Placeholder"
                                    value={question.placeholder ?? ''}
                                    onChange={(e) =>
                                      updateStep(stepIndex, (current) => ({
                                        ...current,
                                        questions: current.questions.map((q, i) =>
                                          i === questionIndex
                                            ? { ...q, placeholder: e.target.value }
                                            : q
                                        ),
                                      }))
                                    }
                                    placeholder="Optional helper text"
                                  />
                                  <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-1">Question Type</label>
                                    <select
                                      value={question.input_type ?? 'text'}
                                      onChange={(e) =>
                                        updateStep(stepIndex, (current) => ({
                                          ...current,
                                          questions: current.questions.map((q, i) =>
                                            i === questionIndex
                                              ? {
                                                  ...q,
                                                  input_type: e.target.value === 'select' ? 'select' : 'text',
                                                  options:
                                                    e.target.value === 'select'
                                                      ? q.options && q.options.length > 0
                                                        ? q.options
                                                        : [{ value: 'option_1', label: '' }]
                                                      : [],
                                                }
                                              : q
                                          ),
                                        }))
                                      }
                                      className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 w-full"
                                    >
                                      <option value="text">Text Input</option>
                                      <option value="select">Dropdown (Single Select)</option>
                                    </select>
                                  </div>
                                  <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-1">Style</label>
                                    <select
                                      value={question.style ?? 'short'}
                                      disabled={question.input_type === 'select'}
                                      onChange={(e) =>
                                        updateStep(stepIndex, (current) => ({
                                          ...current,
                                          questions: current.questions.map((q, i) =>
                                            i === questionIndex
                                              ? {
                                                  ...q,
                                                  style: (e.target.value === 'paragraph' ? 'paragraph' : 'short') as
                                                    | 'short'
                                                    | 'paragraph',
                                                }
                                              : q
                                          ),
                                        }))
                                      }
                                      className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 w-full"
                                    >
                                      <option value="short">Short</option>
                                      <option value="paragraph">Paragraph</option>
                                    </select>
                                  </div>
                                </div>
                                {question.input_type === 'select' && (
                                  <div className="mt-3 space-y-2 rounded border border-slate-700 p-3">
                                    <div className="flex items-center justify-between">
                                      <p className="text-xs text-gray-300">Dropdown Options (max 10)</p>
                                      <Button
                                        size="sm"
                                        onClick={() => addSelectOption(stepIndex, questionIndex)}
                                        disabled={(question.options?.length ?? 0) >= 10}
                                      >
                                        + Add Option
                                      </Button>
                                    </div>
                                    {(question.options ?? []).length === 0 ? (
                                      <p className="text-xs text-gray-500">No options yet.</p>
                                    ) : (
                                      <div className="space-y-2">
                                        {(question.options ?? []).map((option, optionIndex) => (
                                          <div
                                            key={`${question.question_id}-option-${optionIndex}`}
                                            className="flex items-end gap-2"
                                          >
                                            <Input
                                              className="flex-1"
                                              label="Option Label"
                                              value={option.label}
                                              onChange={(e) =>
                                                updateSelectOption(
                                                  stepIndex,
                                                  questionIndex,
                                                  optionIndex,
                                                  e.target.value
                                                )
                                              }
                                              placeholder="Billing Support"
                                            />
                                            <Button
                                              variant="danger"
                                              size="sm"
                                              onClick={() =>
                                                removeSelectOption(
                                                  stepIndex,
                                                  questionIndex,
                                                  optionIndex
                                                )
                                              }
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
                                    onClick={() => removeQuestion(stepIndex, questionIndex)}
                                    disabled={formSaving || formDeleting}
                                  >
                                    Remove Question
                                  </Button>
                                </div>
                              </Card>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-gray-300">Branch Rules</p>
                          <Button
                            size="sm"
                            onClick={() => addBranchRule(stepIndex)}
                            disabled={formSaving || formDeleting || step.questions.length === 0}
                          >
                            + Add Rule
                          </Button>
                        </div>

                        {step.branch_rules.length === 0 ? (
                          <p className="text-xs text-gray-500">No branch rules for this step.</p>
                        ) : (
                          <div className="space-y-2">
                            {step.branch_rules.map((rule, ruleIndex) => (
                              <Card
                                key={`${step.step_number}-rule-${ruleIndex}`}
                                variant="default"
                                padding="sm"
                              >
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                  <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-1">Question</label>
                                    <select
                                      value={rule.question_id}
                                      onChange={(e) =>
                                        updateStep(stepIndex, (current) => ({
                                          ...current,
                                          branch_rules: current.branch_rules.map((r, i) =>
                                            i === ruleIndex
                                              ? { ...r, question_id: e.target.value }
                                              : r
                                          ),
                                        }))
                                      }
                                      className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 w-full"
                                    >
                                      {step.questions.map((question, questionIdx) => (
                                        <option key={question.question_id} value={question.question_id}>
                                          {question.label?.trim() || `Question ${questionIdx + 1}`}
                                        </option>
                                      ))}
                                    </select>
                                  </div>

                                  <Input
                                    label="Regex Match"
                                    value={rule.match_pattern}
                                    onChange={(e) =>
                                      updateStep(stepIndex, (current) => ({
                                        ...current,
                                        branch_rules: current.branch_rules.map((r, i) =>
                                          i === ruleIndex
                                            ? { ...r, match_pattern: e.target.value }
                                            : r
                                        ),
                                      }))
                                    }
                                    placeholder="(?i)billing"
                                  />

                                  <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-1">Next Step</label>
                                    <select
                                      value={rule.next_step_number ?? ''}
                                      onChange={(e) =>
                                        updateStep(stepIndex, (current) => ({
                                          ...current,
                                          branch_rules: current.branch_rules.map((r, i) =>
                                            i === ruleIndex
                                              ? {
                                                  ...r,
                                                  next_step_number: e.target.value
                                                    ? Number.parseInt(e.target.value, 10)
                                                    : null,
                                                }
                                              : r
                                          ),
                                        }))
                                      }
                                      className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 w-full"
                                    >
                                      <option value="">End Flow</option>
                                      {formSteps
                                        .filter((candidate) => candidate.step_number !== step.step_number)
                                        .map((candidate) => (
                                          <option
                                            key={`next-step-${candidate.step_number}`}
                                            value={candidate.step_number}
                                          >
                                            Step {candidate.step_number}
                                          </option>
                                        ))}
                                    </select>
                                  </div>
                                </div>
                                <div className="flex justify-end mt-3">
                                  <Button
                                    variant="danger"
                                    size="sm"
                                    onClick={() => removeBranchRule(stepIndex, ruleIndex)}
                                    disabled={formSaving || formDeleting}
                                  >
                                    Remove Rule
                                  </Button>
                                </div>
                              </Card>
                            ))}
                          </div>
                        )}

                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">Default Next Step</label>
                          <select
                            value={step.default_next_step ?? ''}
                            onChange={(e) =>
                              updateStep(stepIndex, (current) => ({
                                ...current,
                                default_next_step: e.target.value
                                  ? Number.parseInt(e.target.value, 10)
                                  : null,
                              }))
                            }
                            className="bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 w-full"
                          >
                            <option value="">End Flow</option>
                            {formSteps
                              .filter((candidate) => candidate.step_number !== step.step_number)
                              .map((candidate) => (
                                <option
                                  key={`default-next-${candidate.step_number}`}
                                  value={candidate.step_number}
                                >
                                  Step {candidate.step_number}
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
              <Button onClick={addStep} disabled={formSaving || formDeleting}>
                + Add Step
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* ---------------------------------------------------------------- */}
      {/* Category Delete Confirmation */}
      {/* ---------------------------------------------------------------- */}
      <Modal
        open={!!deletingCategory}
        onClose={() => setDeletingCategory(null)}
        title="Delete Category"
        size="sm"
        headerVariant="error"
        footer={
          <ModalFooter>
            <Button
              variant="secondary"
              onClick={() => setDeletingCategory(null)}
              disabled={catDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDeleteCategory}
              loading={catDeleting}
            >
              {catDeleting ? 'Deleting…' : 'Delete'}
            </Button>
          </ModalFooter>
        }
      >
        <p className="text-gray-300">
          Are you sure you want to delete the category{' '}
          <strong className="text-white">{deletingCategory?.name}</strong>? Existing
          tickets in this category will not be affected.
        </p>
      </Modal>
    </div>
  );
}
