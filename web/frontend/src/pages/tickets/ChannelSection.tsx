/**
 * ChannelSection — Expandable section for a ticket channel
 *
 * Displays channel-specific panel settings (title, description, color, button)
 * and associated categories. Allows inline editing and category management.
 */

import { useState } from 'react';
import type { TicketCategory, TicketChannelConfig, TicketChannelConfigUpdate } from '../../api/endpoints';
import SearchableSelect, { type SelectOption } from '../../components/SearchableSelect';
import { Badge, Button, Card, CardBody, Input, Textarea } from '../../components/ui';
import { PanelPreview } from './PanelPreview';

// ---- Inline SVG icons (no external icon library) ----

const ChevronUpIcon = () => (
  <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
  </svg>
);

const ChevronDownIcon = () => (
  <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
);

const HashIcon = () => (
  <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 9h16M4 15h16M10 3l-2 18M16 3l-2 18" />
  </svg>
);

const PencilIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
  </svg>
);

const PencilIconSm = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const TrashIconSm = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

interface ChannelSectionProps {
  config: TicketChannelConfig;
  channelName: string;
  categories: TicketCategory[];
  availableChannels: { id: string; name: string }[];  // Channels not yet configured (excludes current)
  onUpdateConfig: (
    channelId: string,
    updates: TicketChannelConfigUpdate,
  ) => Promise<void>;
  onDeleteConfig: (channelId: string) => Promise<void>;
  onAddCategory: (channelId: string) => void;
  onEditCategory: (category: TicketCategory) => void;
  onDeleteCategory: (category: TicketCategory) => void;
  onOpenFormEditor: (category: TicketCategory) => void;
}

export default function ChannelSection({
  config,
  channelName,
  categories,
  availableChannels,
  onUpdateConfig,
  onDeleteConfig,
  onAddCategory,
  onEditCategory,
  onDeleteCategory,
  onOpenFormEditor,
}: ChannelSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [newChannelId, setNewChannelId] = useState<string>('');

  // Local edit state
  const [panelTitle, setPanelTitle] = useState(config.panel_title);
  const [panelDescription, setPanelDescription] = useState(config.panel_description);
  const [panelColor, setPanelColor] = useState(config.panel_color);
  const [buttonText, setButtonText] = useState(config.button_text);
  const [buttonEmoji, setButtonEmoji] = useState(config.button_emoji || '🎫');
  const [enablePublicButton, setEnablePublicButton] = useState(
    config.enable_public_button,
  );
  const [publicButtonText, setPublicButtonText] = useState(
    config.public_button_text,
  );
  const [publicButtonEmoji, setPublicButtonEmoji] = useState(
    config.public_button_emoji || '🌐',
  );
  const [privateButtonColor, setPrivateButtonColor] = useState(
    config.private_button_color || '',
  );
  const [publicButtonColor, setPublicButtonColor] = useState(
    config.public_button_color || '',
  );
  const [buttonOrder, setButtonOrder] = useState(
    config.button_order || 'private_first',
  );

  // Build channel options for searchable select
  const channelOptions: SelectOption[] = availableChannels.map((ch) => ({
    id: ch.id,
    name: ch.name,
  }));

  const handleSave = async () => {
    setSaving(true);
    try {
      // Only send new_channel_id if it differs from current
      const hasChannelChange = newChannelId && newChannelId !== config.channel_id;

      await onUpdateConfig(config.channel_id, {
        new_channel_id: hasChannelChange ? newChannelId : undefined,
        panel_title: panelTitle,
        panel_description: panelDescription,
        panel_color: panelColor,
        button_text: buttonText,
        button_emoji: buttonEmoji,
        enable_public_button: enablePublicButton,
        public_button_text: publicButtonText,
        public_button_emoji: publicButtonEmoji,
        private_button_color: privateButtonColor || null,
        public_button_color: publicButtonColor || null,
        button_order: buttonOrder,
      });
      setEditing(false);
      setNewChannelId('');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    // Reset to saved values
    setPanelTitle(config.panel_title);
    setPanelDescription(config.panel_description);
    setPanelColor(config.panel_color);
    setButtonText(config.button_text);
    setButtonEmoji(config.button_emoji || '🎫');
    setEnablePublicButton(config.enable_public_button);
    setPublicButtonText(config.public_button_text);
    setPublicButtonEmoji(config.public_button_emoji || '🌐');
    setPrivateButtonColor(config.private_button_color || '');
    setPublicButtonColor(config.public_button_color || '');
    setButtonOrder(config.button_order || 'private_first');
    setNewChannelId('');
    setEditing(false);
  };

  const handleDelete = async () => {
    if (
      !confirm(
        `Delete channel config for #${channelName}?\n\nCategories will become unassigned (you'll need to reassign them).`,
      )
    ) {
      return;
    }

    setDeleting(true);
    try {
      await onDeleteConfig(config.channel_id);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card className="mb-4">
      <CardBody>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
              aria-label={expanded ? 'Collapse' : 'Expand'}
            >
              {expanded ? <ChevronUpIcon /> : <ChevronDownIcon />}
            </button>
            <HashIcon />
            <h3 className="text-lg font-semibold text-white">{channelName}</h3>
            <Badge variant="info">
              {categories.length} {categories.length === 1 ? 'category' : 'categories'}
            </Badge>
          </div>

          <div className="flex items-center gap-2">
            {!editing && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setEditing(true)}
                  leftIcon={<PencilIcon />}
                >
                  Edit Panel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={handleDelete}
                  loading={deleting}
                  leftIcon={<TrashIcon />}
                  disabled={saving}
                />
              </>
            )}
            {editing && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCancel}
                  disabled={saving}
                >
                  ✕ Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSave}
                  loading={saving}
                >
                  💾 Save
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Expanded Content */}
        {expanded && (
          <div className="space-y-6 mt-4">
            {/* Channel Assignment */}
            {editing && availableChannels.length > 0 && (
              <div className="p-4 bg-blue-900/20 border border-blue-700/50 rounded">
                <h5 className="text-sm font-semibold text-blue-300 mb-1">Discord Channel</h5>
                <p className="text-xs text-gray-400 mb-3">
                  Currently assigned to <span className="font-medium text-blue-200">#{channelName}</span>. Type to move this panel to a different channel — all categories will move with it.
                </p>
                <SearchableSelect
                  options={channelOptions}
                  selected={newChannelId}
                  onChange={(id) => setNewChannelId(id ?? '')}
                  placeholder="Search channels to move…"
                />
              </div>
            )}

            {/* Panel Customization */}
            <div>
              <h4 className="text-sm font-semibold text-gray-300 mb-3">Panel Settings</h4>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Left: Form Inputs */}
                <div className="space-y-4">
                  <Input
                    label="Panel Title"
                    value={panelTitle}
                    onChange={(e) => setPanelTitle(e.target.value)}
                    placeholder="🎫 Support Tickets"
                    disabled={!editing}
                  />

                  <Textarea
                    label="Panel Description"
                    value={panelDescription}
                    onChange={(e) => setPanelDescription(e.target.value)}
                    placeholder="Click the button below to open a support ticket..."
                    rows={4}
                    disabled={!editing}
                  />

                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label="Panel Color"
                      value={panelColor}
                      onChange={(e) => setPanelColor(e.target.value)}
                      placeholder="0099FF"
                      disabled={!editing}
                    />
                    <Input
                      label="Button Emoji"
                      value={buttonEmoji}
                      onChange={(e) => setButtonEmoji(e.target.value)}
                      placeholder="🎫"
                      disabled={!editing}
                      className="text-center"
                    />
                  </div>

                  <Input
                    label="Private Button Text"
                    value={buttonText}
                    onChange={(e) => setButtonText(e.target.value)}
                    placeholder="Create Ticket"
                    disabled={!editing}
                  />

                  <label className="flex items-center gap-2 text-sm text-gray-300">
                    <input
                      type="checkbox"
                      checked={enablePublicButton}
                      onChange={(e) => setEnablePublicButton(e.target.checked)}
                      disabled={!editing}
                      className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-blue-500 focus:ring-blue-500/40"
                    />
                    Enable Public Ticket Button
                  </label>

                  {enablePublicButton && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <Input
                        label="Public Button Text"
                        value={publicButtonText}
                        onChange={(e) => setPublicButtonText(e.target.value)}
                        placeholder="Create Public Ticket"
                        disabled={!editing}
                      />
                      <Input
                        label="Public Button Emoji"
                        value={publicButtonEmoji}
                        onChange={(e) => setPublicButtonEmoji(e.target.value)}
                        placeholder="🌐"
                        disabled={!editing}
                        className="text-center"
                      />
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Input
                      label="Private Button Color (Hex)"
                      value={privateButtonColor}
                      onChange={(e) => setPrivateButtonColor(e.target.value)}
                      placeholder="5865F2 (Blue)"
                      disabled={!editing}
                    />
                    {enablePublicButton && (
                      <Input
                        label="Public Button Color (Hex)"
                        value={publicButtonColor}
                        onChange={(e) => setPublicButtonColor(e.target.value)}
                        placeholder="4F545C (Gray)"
                        disabled={!editing}
                      />
                    )}
                  </div>

                  {enablePublicButton && (
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Button Order
                      </label>
                      <select
                        value={buttonOrder}
                        onChange={(e) => setButtonOrder(e.target.value)}
                        disabled={!editing}
                        className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="private_first">Private First, Public Second</option>
                        <option value="public_first">Public First, Private Second</option>
                      </select>
                    </div>
                  )}
                </div>

                {/* Right: Live Preview */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Live Preview
                  </label>
                  <PanelPreview
                    title={panelTitle}
                    description={panelDescription}
                    color={panelColor}
                    buttonText={buttonText}
                    buttonEmoji={buttonEmoji}
                    enablePublicButton={enablePublicButton}
                    publicButtonText={publicButtonText}
                    publicButtonEmoji={publicButtonEmoji}
                    privateButtonColor={privateButtonColor}
                    publicButtonColor={publicButtonColor}
                    buttonOrder={buttonOrder}
                  />
                </div>
              </div>
            </div>

            {/* Categories */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-gray-300">Categories</h4>
                <Button
                  size="sm"
                  onClick={() => onAddCategory(config.channel_id)}
                >
                  + Add Category
                </Button>
              </div>

              {categories.length === 0 ? (
                <p className="text-sm text-gray-500 italic">
                  No categories yet. Add one to get started.
                </p>
              ) : (
                <div className="space-y-2">
                  {categories.map((cat) => (
                    <div
                      key={cat.id}
                      className="flex items-center justify-between p-3 bg-gray-700/50 rounded border border-gray-600/50"
                    >
                      <div className="flex items-center gap-3">
                        {cat.emoji && <span className="text-xl">{cat.emoji}</span>}
                        <div>
                          <p className="font-medium text-white">{cat.name}</p>
                          {cat.description && (
                            <p className="text-xs text-gray-400">{cat.description}</p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => onOpenFormEditor(cat)}
                        >
                          Form
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => onEditCategory(cat)}
                          leftIcon={<PencilIconSm />}
                        />
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => onDeleteCategory(cat)}
                          leftIcon={<TrashIconSm />}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
