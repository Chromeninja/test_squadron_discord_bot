/** Category create/edit modal. */

import type {
  TicketCategory,
  TicketCategoryEligibilityStatus,
} from '../../api/endpoints';
import type { MultiSelectOption } from '../../components/SearchableMultiSelect';
import SearchableMultiSelect from '../../components/SearchableMultiSelect';
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
  catSaving: boolean;
  roleOptions: MultiSelectOption[];
  onCatNameChange: (v: string) => void;
  onCatDescriptionChange: (v: string) => void;
  onCatEmojiChange: (v: string) => void;
  onCatWelcomeMessageChange: (v: string) => void;
  onCatRoleIdsChange: (v: string[]) => void;
  onCatAllowedStatusesChange: (v: TicketCategoryEligibilityStatus[]) => void;
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
  catSaving,
  roleOptions,
  onCatNameChange,
  onCatDescriptionChange,
  onCatEmojiChange,
  onCatWelcomeMessageChange,
  onCatRoleIdsChange,
  onCatAllowedStatusesChange,
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
          placeholder="e.g. 📩"
          helperText="Single emoji shown in the dropdown."
        />
        <Textarea
          label="Description"
          value={catDescription}
          onChange={(e) => onCatDescriptionChange(e.target.value)}
          placeholder="Brief description shown in the category dropdown."
          rows={2}
        />
        <DiscordMarkdownEditor
          label="Welcome Message"
          value={catWelcomeMessage}
          onChange={onCatWelcomeMessageChange}
          placeholder="Custom welcome message for tickets in this category. Leave empty to use the default."
          rows={3}
          helperText="Category welcome messages support Discord markdown (bold, bullets, italics, quotes, code, links)."
        />
        <div>
          <h5 className="text-sm font-medium text-gray-300 mb-1">Eligibility Requirements</h5>
          <p className="text-xs text-gray-500 mb-2">
            Select who can open this category. If any are selected, users must match at
            least one selected requirement. Leave all unchecked for no restriction.
          </p>
          <div className="space-y-2">
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
        <div>
          <h5 className="text-sm font-medium text-gray-300 mb-1">Notified Roles</h5>
          <p className="text-xs text-gray-500 mb-2">
            Roles mentioned in ticket threads for this category. Members with these
            roles can claim/close tickets in this category. If empty, global Staff
            Roles are mentioned instead.
          </p>
          <SearchableMultiSelect
            options={roleOptions}
            selected={catRoleIds}
            onChange={onCatRoleIdsChange}
            placeholder="Search roles…"
            componentId="cat-role-ids"
          />
        </div>
      </div>
    </Modal>
  );
}
