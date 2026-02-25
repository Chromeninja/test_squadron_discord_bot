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
import { handleApiError, showSuccess } from '../utils/toast';

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
  const [catSaving, setCatSaving] = useState(false);
  const [catDeleting, setCatDeleting] = useState(false);

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
            <Textarea
              value={panelDescription}
              onChange={(e) => setPanelDescription(e.target.value)}
              placeholder="Click the button below to create a support ticket."
              rows={3}
            />
          </div>

          {/* Close Message */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Close Message</h5>
            <p className="text-xs text-gray-500 mb-2">
              Message displayed when a ticket is closed.
            </p>
            <Textarea
              value={closeMessage}
              onChange={(e) => setCloseMessage(e.target.value)}
              placeholder="This ticket has been closed."
              rows={2}
            />
          </div>

          {/* Default Welcome Message */}
          <div>
            <h5 className="text-sm font-medium text-gray-300 mb-1">Default Welcome Message</h5>
            <p className="text-xs text-gray-500 mb-2">
              Welcome message for new tickets without a category-specific message.
            </p>
            <Textarea
              value={defaultWelcomeMessage}
              onChange={(e) => setDefaultWelcomeMessage(e.target.value)}
              placeholder="Welcome to your support ticket! Please describe your issue…"
              rows={3}
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
          <Textarea
            label="Welcome Message"
            value={catWelcomeMessage}
            onChange={(e) => setCatWelcomeMessage(e.target.value)}
            placeholder="Custom welcome message for tickets in this category. Leave empty to use the default."
            rows={3}
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
