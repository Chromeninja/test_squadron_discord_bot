/**
 * Ticket System management page.
 *
 * Orchestrates data-fetching and delegates rendering to focused
 * sub-components located in `./tickets/`.
 *
 * AI Notes:
 * Layout follows a channel-first approach: users add channels, then
 * each channel gets its own panel config + categories via ChannelSection.
 * Global settings (log channel, staff roles, ticket messages) remain in a
 * separate collapsible section.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  DiscordChannel,
  GuildRole,
  TicketCategory,
  TicketChannelConfig,
  TicketChannelConfigUpdate,
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
  Button,
  Card,
  CardBody,
  Spinner,
} from '../components/ui';
import DiscordMarkdownEditor from '../components/DiscordMarkdownEditor';
import { handleApiError, showSuccess } from '../utils/toast';

import {
  CategoryModal,
  ChannelAddModal,
  ChannelSection,
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

  // --- Channel configs state (per-channel panel customization) ---
  const [channelConfigs, setChannelConfigs] = useState<TicketChannelConfig[]>([]);
  const [channelAddModalOpen, setChannelAddModalOpen] = useState(false);

  // --- Settings state ---
  const [logChannelId, setLogChannelId] = useState<string | null>(null);
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
  const [catPrerequisiteRoleIdsAll, setCatPrerequisiteRoleIdsAll] = useState<
    string[]
  >([]);
  const [catPrerequisiteRoleIdsAny, setCatPrerequisiteRoleIdsAny] = useState<
    string[]
  >([]);
  const [createCategoryChannelId, setCreateCategoryChannelId] =
    useState<string>('0');
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

  /** Channels not yet configured for ticketing (available to add). */
  const availableChannels: MultiSelectOption[] = useMemo(() => {
    const configuredIds = new Set(channelConfigs.map((c) => c.channel_id));
    return channels
      .filter((c) => !configuredIds.has(c.id))
      .map((c) => ({ id: c.id, name: c.name }));
  }, [channels, channelConfigs]);

  /** Categories grouped by channel_id for rendering inside ChannelSections. */
  const categoriesByChannel = useMemo(() => {
    const map = new Map<string, TicketCategory[]>();
    for (const cat of categories) {
      const key = cat.channel_id ?? '0';
      const list = map.get(key) ?? [];
      list.push(cat);
      map.set(key, list);
    }
    return map;
  }, [categories]);

  // -----------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [settingsRes, catsRes, statsRes, channelsRes, rolesRes, channelConfigsRes] =
        await Promise.all([
          ticketsApi.getSettings(),
          ticketsApi.getCategories(),
          ticketsApi.getStats(),
          guildApi.getDiscordChannels(guildId),
          guildApi.getDiscordRoles(guildId),
          ticketsApi.getChannelConfigs(),
        ]);

      if (!isMountedRef.current) return;

      const s = settingsRes.settings;
      setLogChannelId(s.log_channel_id);
      setCloseMessage(s.close_message ?? '');
      setStaffRoles(s.staff_roles);
      setDefaultWelcomeMessage(s.default_welcome_message ?? '');
      setCategories(catsRes.categories);
      setStatsOpen(statsRes.open);
      setStatsClosed(statsRes.closed);
      setStatsTotal(statsRes.total);
      setChannels(channelsRes.channels);
      setRoles(rolesRes.roles);
      setChannelConfigs(channelConfigsRes.channels);
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
  // Channel config handlers
  // -----------------------------------------------------------------

  const handleAddChannels = async (channelIds: string[]) => {
    try {
      for (const channelId of channelIds) {
        await ticketsApi.createChannelConfig({
          guild_id: guildId,
          channel_id: channelId,
        });
      }
      const res = await ticketsApi.getChannelConfigs();
      if (isMountedRef.current) setChannelConfigs(res.channels);
      showSuccess(
        `Added ${channelIds.length} channel${channelIds.length === 1 ? '' : 's'}`,
      );
    } catch (err) {
      handleApiError(err, 'Failed to add channel');
    }
  };

  const handleUpdateChannelConfig = async (
    channelId: string,
    updates: TicketChannelConfigUpdate,
  ) => {
    try {
      const hasChannelChange = updates.new_channel_id && updates.new_channel_id !== channelId;

      await ticketsApi.updateChannelConfig(channelId, {
        new_channel_id: updates.new_channel_id,
        panel_title: updates.panel_title,
        panel_description: updates.panel_description,
        panel_color: updates.panel_color,
        button_text: updates.button_text,
        button_emoji: updates.button_emoji,
        enable_public_button: updates.enable_public_button,
        public_button_text: updates.public_button_text,
        public_button_emoji: updates.public_button_emoji,
        private_button_color: updates.private_button_color,
        public_button_color: updates.public_button_color,
        button_order: updates.button_order,
      });

      const res = await ticketsApi.getChannelConfigs();
      setChannelConfigs(res.channels);
      showSuccess(hasChannelChange ? 'Channel moved and panel updated' : 'Channel panel updated');
    } catch (err) {
      handleApiError(err, 'Failed to update channel config');
    }
  };

  const handleDeleteChannelConfig = async (channelId: string) => {
    try {
      await ticketsApi.deleteChannelConfig(channelId);
      setChannelConfigs((prev) =>
        prev.filter((c) => c.channel_id !== channelId),
      );
      showSuccess('Channel removed');
    } catch (err) {
      handleApiError(err, 'Failed to remove channel');
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
    setCatPrerequisiteRoleIdsAll([]);
    setCatPrerequisiteRoleIdsAny([]);
    setCreateCategoryChannelId('0');
  };

  const openCreateCategory = (channelId?: string) => {
    setEditingCategory(null);
    resetCategoryForm();
    if (channelId) setCreateCategoryChannelId(channelId);
    setCategoryModalOpen(true);
  };

  const openEditCategory = (cat: TicketCategory) => {
    setEditingCategory(cat);
    setCatName(cat.name);
    setCatDescription(cat.description);
    setCatEmoji(cat.emoji ?? '');
    setCatWelcomeMessage(cat.welcome_message);
    setCatRoleIds(cat.role_ids);
    setCatPrerequisiteRoleIdsAll(cat.prerequisite_role_ids_all ?? []);
    setCatPrerequisiteRoleIdsAny(cat.prerequisite_role_ids_any ?? []);
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
          prerequisite_role_ids_all: catPrerequisiteRoleIdsAll,
          prerequisite_role_ids_any: catPrerequisiteRoleIdsAny,
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
          prerequisite_role_ids_all: catPrerequisiteRoleIdsAll,
          prerequisite_role_ids_any: catPrerequisiteRoleIdsAny,
          channel_id: createCategoryChannelId,
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

      {/* Statistics — compact inline bar */}
      <TicketStats open={statsOpen} closed={statsClosed} total={statsTotal} />

      {/* Channels — primary setup area */}
      <AccordionSection title="Channels" defaultOpen>
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <p className="text-sm text-gray-400 sm:pr-4">
              Each channel gets its own ticket panel with customizable
              appearance. Add categories under each channel for users to
              choose from.
            </p>
            <Button
              size="sm"
              onClick={() => setChannelAddModalOpen(true)}
              className="self-start sm:self-auto flex-shrink-0"
            >
              + Add Channel
            </Button>
          </div>

          {channelConfigs.length === 0 ? (
            <Alert variant="info">
              No channels configured yet — add one to get started.
            </Alert>
          ) : (
            <div className="space-y-4">
              {channelConfigs.map((config) => {
                const ch = channels.find((c) => c.id === config.channel_id);
                // Available channels = unconfigured + other configured channels (for swapping)
                const availableForThis = channels
                  .filter((c) => c.id !== config.channel_id && !channelConfigs.some(cfg => cfg.channel_id === c.id))
                  .map((c) => ({ id: c.id, name: c.name }));
                return (
                  <ChannelSection
                    key={config.channel_id}
                    config={config}
                    channelName={ch?.name ?? `Unknown (${config.channel_id})`}
                    categories={categoriesByChannel.get(config.channel_id) ?? []}
                    availableChannels={availableForThis}
                    onUpdateConfig={handleUpdateChannelConfig}
                    onDeleteConfig={handleDeleteChannelConfig}
                    onAddCategory={(chId) => openCreateCategory(chId)}
                    onEditCategory={openEditCategory}
                    onDeleteCategory={setDeletingCategory}
                    onOpenFormEditor={openFollowUpEditor}
                  />
                );
              })}
            </div>
          )}

          {/* Unassigned categories warning */}
          {(categoriesByChannel.get('0')?.length ?? 0) > 0 && (
            <Alert variant="warning">
              <span className="font-medium">
                {categoriesByChannel.get('0')!.length} unassigned{' '}
                {categoriesByChannel.get('0')!.length === 1
                  ? 'category'
                  : 'categories'}
              </span>{' '}
              — these won&apos;t appear on any panel. Create categories from a channel
              section to assign them.
            </Alert>
          )}

          {/* Deploy action */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 pt-3 border-t border-slate-700">
            <Button
              variant="success"
              onClick={handleDeployPanel}
              loading={deploying}
              disabled={channelConfigs.length === 0}
              className="self-start"
            >
              {deploying ? 'Deploying…' : '🚀 Deploy Panels'}
            </Button>
            <span className="text-xs text-gray-500">
              {channelConfigs.length === 0
                ? 'Add at least one channel first.'
                : 'Posts or updates the ticket panel in each configured channel.'}
            </span>
          </div>
        </div>
      </AccordionSection>

      {/* Settings — secondary, collapsed by default */}
      <AccordionSection title="Settings">
        <div className="space-y-6">

          {/* Behavior group */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h5 className="text-sm font-medium text-gray-300 mb-1">Log Channel</h5>
              <p className="text-xs text-gray-500 mb-2">
                Channel where ticket open/close events are logged.
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
                Global admins that can claim/close any ticket. Used when a
                category has no Notified Roles.
              </p>
              <SearchableMultiSelect
                options={roleOptions}
                selected={staffRoles}
                onChange={setStaffRoles}
                placeholder="Search roles…"
                componentId="ticket-staff-roles"
              />
            </div>
          </div>

          {/* Messages group */}
          <div className="border-t border-slate-700 pt-5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Messages</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h5 className="text-sm font-medium text-gray-300 mb-1">Close Message</h5>
                <p className="text-xs text-gray-500 mb-2">
                  Sent when a ticket is closed.
                </p>
                <DiscordMarkdownEditor
                  value={closeMessage}
                  onChange={setCloseMessage}
                  placeholder="This ticket has been closed."
                  rows={2}
                />
              </div>

              <div>
                <h5 className="text-sm font-medium text-gray-300 mb-1">Default Welcome Message</h5>
                <p className="text-xs text-gray-500 mb-2">
                  Used when a category has no custom welcome message.
                </p>
                <DiscordMarkdownEditor
                  value={defaultWelcomeMessage}
                  onChange={setDefaultWelcomeMessage}
                  placeholder="Welcome to your support ticket! Please describe your issue…"
                  rows={3}
                />
              </div>
            </div>
          </div>

          <div className="pt-2">
            <Button onClick={handleSaveSettings} loading={saving}>
              {saving ? 'Saving…' : 'Save Settings'}
            </Button>
          </div>
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

      {/* Channel Add Modal */}
      <ChannelAddModal
        open={channelAddModalOpen}
        onClose={() => setChannelAddModalOpen(false)}
        availableChannels={availableChannels}
        onAdd={handleAddChannels}
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
        catPrerequisiteRoleIdsAll={catPrerequisiteRoleIdsAll}
        catPrerequisiteRoleIdsAny={catPrerequisiteRoleIdsAny}
        catSaving={catSaving}
        roleOptions={roleOptions}
        onCatNameChange={setCatName}
        onCatDescriptionChange={setCatDescription}
        onCatEmojiChange={setCatEmoji}
        onCatWelcomeMessageChange={setCatWelcomeMessage}
        onCatRoleIdsChange={setCatRoleIds}
        onCatPrerequisiteRoleIdsAllChange={setCatPrerequisiteRoleIdsAll}
        onCatPrerequisiteRoleIdsAnyChange={setCatPrerequisiteRoleIdsAny}
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
