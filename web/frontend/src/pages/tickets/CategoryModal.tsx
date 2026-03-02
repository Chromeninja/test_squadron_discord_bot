/** Category create/edit modal. */

import type {
  TicketCategory,
  TicketCategoryEligibilityStatus,
} from '../../api/endpoints';
import type { MultiSelectOption } from '../../components/SearchableMultiSelect';
import type { SelectOption } from '../../components/SearchableSelect';
import SearchableMultiSelect from '../../components/SearchableMultiSelect';
import SearchableSelect from '../../components/SearchableSelect';
import DiscordMarkdownEditor from '../../components/DiscordMarkdownEditor';
import { Button, Input, Modal, ModalFooter, Textarea } from '../../components/ui';

interface CategoryModalProps {
  open: boolean;
  onClose: () => void;
  editingCategory: TicketCategory | null;
  catName: string;
  catDescription: string;
  catEmoji: string;
  catWelcomeMessage: string;
  catRoleIds: string[];
  catAllowedStatuses: TicketCategoryEligibilityStatus[];
  catChannelId: string;
  catSaving: boolean;
  roleOptions: MultiSelectOption[];
  channelOptions: SelectOption[];
  onCatNameChange: (v: string) => void;
  onCatDescriptionChange: (v: string) => void;
  onCatEmojiChange: (v: string) => void;
  onCatWelcomeMessageChange: (v: string) => void;
  onCatRoleIdsChange: (v: string[]) => void;
  onCatAllowedStatusesChange: (v: TicketCategoryEligibilityStatus[]) => void;
  onCatChannelIdChange: (v: string) => void;
  onSave: () => void;
}

export default function CategoryModal({
  open,
  onClose,
  editingCategory,
  catName,
  catDescription,
  catEmoji,
  catWelcomeMessage,
  catRoleIds,
  catAllowedStatuses,
  catChannelId,
  catSaving,
  roleOptions,
  channelOptions,
  onCatNameChange,
  onCatDescriptionChange,
  onCatEmojiChange,
  onCatWelcomeMessageChange,
  onCatRoleIdsChange,
  onCatAllowedStatusesChange,
  onCatChannelIdChange,
  onSave,
}: CategoryModalProps) {
  const toggleAllowedStatus = (status: TicketCategoryEligibilityStatus) => {
    if (catAllowedStatuses.includes(status)) {
      onCatAllowedStatusesChange(catAllowedStatuses.filter((value) => value !== status));
      return;
    }
    onCatAllowedStatusesChange([...catAllowedStatuses, status]);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingCategory ? 'Edit Category' : 'New Category'}
      size="md"
      footer={
        <ModalFooter>
          <Button variant="secondary" onClick={onClose} disabled={catSaving}>
            Cancel
          </Button>
          <Button onClick={onSave} loading={catSaving} disabled={!catName.trim()}>
            {catSaving ? 'Saving…' : editingCategory ? 'Update' : 'Create'}
          </Button>
        </ModalFooter>
      }
    >
      <div className="space-y-4">
        {/* --- Basics --- */}
        <div className="grid grid-cols-[1fr_auto] gap-4">
          <Input
            label="Name"
            value={catName}
            onChange={(e) => onCatNameChange(e.target.value)}
            placeholder="e.g. General Support"
          />
          <Input
            label="Emoji"
            value={catEmoji}
            onChange={(e) => onCatEmojiChange(e.target.value)}
            placeholder="📩"
            className="w-20 text-center"
          />
        </div>

        <div>
          <h5 className="text-sm font-medium text-gray-300 mb-1">Panel Channel</h5>
          <p className="text-xs text-gray-500 mb-2">
            Which channel this category&apos;s &quot;Create Ticket&quot; panel lives in.
          </p>
          <SearchableSelect
            options={channelOptions}
            selected={catChannelId === '0' ? null : catChannelId}
            onChange={(v) => onCatChannelIdChange(v ?? '0')}
            placeholder="Select a channel…"
          />
        </div>

        <Textarea
          label="Description"
          value={catDescription}
          onChange={(e) => onCatDescriptionChange(e.target.value)}
          placeholder="Brief description shown in the category dropdown."
          rows={2}
        />

        {/* --- Messages --- */}
        <div className="border-t border-slate-700 pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Welcome Message</h4>
          <DiscordMarkdownEditor
            value={catWelcomeMessage}
            onChange={onCatWelcomeMessageChange}
            placeholder="Leave empty to use the global default welcome message."
            rows={3}
          />
        </div>

        {/* --- Access control --- */}
        <div className="border-t border-slate-700 pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Access &amp; Notifications</h4>

          <div className="space-y-4">
            <div>
              <h5 className="text-sm font-medium text-gray-300 mb-1">Notified Roles</h5>
              <p className="text-xs text-gray-500 mb-2">
                Mentioned in ticket threads and can claim/close tickets. Falls
                back to global Staff Roles if empty.
              </p>
              <SearchableMultiSelect
                options={roleOptions}
                selected={catRoleIds}
                onChange={onCatRoleIdsChange}
                placeholder="Search roles…"
                componentId="cat-role-ids"
              />
            </div>

            <div>
              <h5 className="text-sm font-medium text-gray-300 mb-1">Eligibility</h5>
              <p className="text-xs text-gray-500 mb-2">
                Restrict who can open this category. Leave all unchecked for no restriction.
              </p>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-gray-200">
                  <input
                    type="checkbox"
                    checked={catAllowedStatuses.includes('bot_verified')}
                    onChange={() => toggleAllowedStatus('bot_verified')}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
                  />
                  Bot Verified
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-200">
                  <input
                    type="checkbox"
                    checked={catAllowedStatuses.includes('org_main')}
                    onChange={() => toggleAllowedStatus('org_main')}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
                  />
                  Org Main
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-200">
                  <input
                    type="checkbox"
                    checked={catAllowedStatuses.includes('org_affiliate')}
                    onChange={() => toggleAllowedStatus('org_affiliate')}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
                  />
                  Org Affiliate
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
