/**
 * Ticket System management page.
 *
 * Orchestrates data-fetching and delegates rendering to focused
 * sub-components located in `./tickets/`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  DiscordChannel,
  GuildRole,
  TicketCategory,
  TicketCategoryEligibilityStatus,
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
  Spinner,
} from '../components/ui';
import DiscordMarkdownEditor from '../components/DiscordMarkdownEditor';
import { handleApiError, showSuccess } from '../utils/toast';

import {
  CategoryModal,
  DeleteCategoryModal,
  FormEditorModal,
  TicketList,
  TicketStats,
  MAX_FORM_STEPS,
  MAX_TOTAL_FOLLOW_UP_QUESTIONS,
  TICKET_PAGE_SIZE,
  normalizeStepsForSave,
} from './tickets';

interface TicketsProps {
  guildId: string;
}

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
  const [catAllowedStatuses, setCatAllowedStatuses] = useState<
    TicketCategoryEligibilityStatus[]
  >([]);
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
    [channels],
  );

  const roleOptions: MultiSelectOption[] = useMemo(
    () => roles.map((r) => ({ id: r.id, name: r.name })),
    [roles],
  );

  // -----------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------

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

      const s = settingsRes.settings;
      setChannelId(s.channel_id);
      setLogChannelId(s.log_channel_id);
      setPanelTitle(s.panel_title ?? '');
      setPanelDescription(s.panel_description ?? '');
      setCloseMessage(s.close_message ?? '');
      setStaffRoles(s.staff_roles);
      setDefaultWelcomeMessage(s.default_welcome_message ?? '');
      setCategories(catsRes.categories);
      setStatsOpen(statsRes.open);
      setStatsClosed(statsRes.closed);
      setStatsTotal(statsRes.total);
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

  const fetchTickets = useCallback(async () => {
    try {
      const res = await ticketsApi.listTickets(
        ticketFilter || undefined,
        ticketPage,
        TICKET_PAGE_SIZE,
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

  // -----------------------------------------------------------------
  // Settings handlers
  // -----------------------------------------------------------------

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

  // -----------------------------------------------------------------
  // Category handlers
  // -----------------------------------------------------------------

  const resetCategoryForm = () => {
    setCatName('');
    setCatDescription('');
    setCatEmoji('');
    setCatWelcomeMessage('');
    setCatRoleIds([]);
    setCatAllowedStatuses([]);
  };

  const openCreateCategory = () => {
    setEditingCategory(null);
    resetCategoryForm();
    setCategoryModalOpen(true);
  };

  const openEditCategory = (cat: TicketCategory) => {
    setEditingCategory(cat);
    setCatName(cat.name);
    setCatDescription(cat.description);
    setCatEmoji(cat.emoji ?? '');
    setCatWelcomeMessage(cat.welcome_message);
    setCatRoleIds(cat.role_ids);
    setCatAllowedStatuses(cat.allowed_statuses ?? []);
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
          allowed_statuses: catAllowedStatuses,
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
          allowed_statuses: catAllowedStatuses,
        });
        showSuccess('Category created');
      }
      setCategoryModalOpen(false);
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

  // -----------------------------------------------------------------
  // Follow-up form handlers
  // -----------------------------------------------------------------

  const openFollowUpEditor = async (category: TicketCategory) => {
    setFormCategory(category);
    setFormEditorOpen(true);
    setFormLoading(true);
    setFormError(null);
    setFormValidationErrors([]);

    try {
      const res = await ticketsApi.getCategoryForm(category.id);
      const sorted = [...(res.config?.steps ?? [])].sort(
        (a, b) => a.step_number - b.step_number,
      );
      setFormSteps(
        sorted.map((step) => ({
          ...step,
          questions: step.questions.map((question) => ({
            ...question,
            input_type: 'text',
            options: [],
          })),
        })),
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

  const runFormValidation = async (categoryId: number): Promise<boolean> => {
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

    // Quick client-side sanity check (full validation is done server-side)
    const total = normalized.reduce((acc, step) => acc + step.questions.length, 0);
    if (normalized.length > MAX_FORM_STEPS) {
      setFormError(`Maximum ${MAX_FORM_STEPS} steps allowed.`);
      return;
    }
    if (total > MAX_TOTAL_FOLLOW_UP_QUESTIONS) {
      setFormError(`Maximum ${MAX_TOTAL_FOLLOW_UP_QUESTIONS} total questions allowed.`);
      return;
    }

    setFormSaving(true);
    try {
      await ticketsApi.updateCategoryForm(formCategory.id, { steps: normalized });
      const isValid = await runFormValidation(formCategory.id);
      showSuccess(
        isValid
          ? 'Follow-up questions saved'
          : 'Follow-up questions saved with validation warnings',
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

      if (apiErrors.length > 0) {
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

  // -----------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------

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

      {/* Statistics */}
      <TicketStats open={statsOpen} closed={statsClosed} total={statsTotal} />

      {/* Settings */}
      <AccordionSection title="Settings" defaultOpen>
        <div className="space-y-6">
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

          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Staff Roles</h5>
            <p className="text-xs text-gray-500 mb-2">
              Global ticket admins that can claim and close any ticket. These roles are
              mentioned only when a category does not define Notified Roles.
            </p>
            <SearchableMultiSelect
              options={roleOptions}
              selected={staffRoles}
              onChange={setStaffRoles}
              placeholder="Search roles…"
              componentId="ticket-staff-roles"
            />
          </div>

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

      {/* Categories */}
      <AccordionSection title="Categories">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">
              Ticket categories let users choose a topic when creating a ticket.
              Each category can have its own welcome message and notified roles.
              Category notified roles can claim/close tickets in that category and are
              the roles mentioned for those tickets.
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
                      {(cat.allowed_statuses?.length ?? 0) > 0 && (
                        <Badge variant="primary-outline" className="ml-2">
                          Requires: {cat.allowed_statuses.join(', ')}
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

      {/* Ticket List */}
      <TicketList
        tickets={tickets}
        categories={categories}
        ticketFilter={ticketFilter}
        ticketPage={ticketPage}
        ticketTotal={ticketTotal}
        onFilterChange={setTicketFilter}
        onPageChange={setTicketPage}
      />

      {/* Category Create/Edit Modal */}
      <CategoryModal
        open={categoryModalOpen}
        onClose={() => setCategoryModalOpen(false)}
        editingCategory={editingCategory}
        catName={catName}
        catDescription={catDescription}
        catEmoji={catEmoji}
        catWelcomeMessage={catWelcomeMessage}
        catRoleIds={catRoleIds}
        catAllowedStatuses={catAllowedStatuses}
        catSaving={catSaving}
        roleOptions={roleOptions}
        onCatNameChange={setCatName}
        onCatDescriptionChange={setCatDescription}
        onCatEmojiChange={setCatEmoji}
        onCatWelcomeMessageChange={setCatWelcomeMessage}
        onCatRoleIdsChange={setCatRoleIds}
        onCatAllowedStatusesChange={setCatAllowedStatuses}
        onSave={handleSaveCategory}
      />

      {/* Follow-up Questions Editor */}
      <FormEditorModal
        open={formEditorOpen}
        category={formCategory}
        steps={formSteps}
        loading={formLoading}
        saving={formSaving}
        deleting={formDeleting}
        error={formError}
        validationErrors={formValidationErrors}
        onClose={closeFollowUpEditor}
        onSave={handleSaveFollowUpForm}
        onDelete={handleDeleteFollowUpForm}
        onStepsChange={setFormSteps}
        onError={setFormError}
      />

      {/* Delete Confirmation */}
      <DeleteCategoryModal
        category={deletingCategory}
        deleting={catDeleting}
        onClose={() => setDeletingCategory(null)}
        onConfirm={handleDeleteCategory}
      />
    </div>
  );
}
