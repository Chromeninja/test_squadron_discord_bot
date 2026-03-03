/** Category create/edit modal. */

import type {
  TicketCategory,
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
  catPrerequisiteRoleIdsAll: string[];
  catPrerequisiteRoleIdsAny: string[];
  catSaving: boolean;
  roleOptions: MultiSelectOption[];
  onCatNameChange: (v: string) => void;
  onCatDescriptionChange: (v: string) => void;
  onCatEmojiChange: (v: string) => void;
  onCatWelcomeMessageChange: (v: string) => void;
  onCatRoleIdsChange: (v: string[]) => void;
  onCatPrerequisiteRoleIdsAllChange: (v: string[]) => void;
  onCatPrerequisiteRoleIdsAnyChange: (v: string[]) => void;
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
  catPrerequisiteRoleIdsAll,
  catPrerequisiteRoleIdsAny,
  catSaving,
  roleOptions,
  onCatNameChange,
  onCatDescriptionChange,
  onCatEmojiChange,
  onCatWelcomeMessageChange,
  onCatRoleIdsChange,
  onCatPrerequisiteRoleIdsAllChange,
  onCatPrerequisiteRoleIdsAnyChange,
  onSave,
}: CategoryModalProps) {
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
                Restrict who can open this category. Leave both empty for no restriction.
              </p>
              <div className="space-y-3">
                <div>
                  <h6 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
                    Must Have ALL
                  </h6>
                  <SearchableMultiSelect
                    options={roleOptions}
                    selected={catPrerequisiteRoleIdsAll}
                    onChange={onCatPrerequisiteRoleIdsAllChange}
                    placeholder="Search required roles…"
                    componentId="cat-prerequisite-role-ids-all"
                  />
                </div>

                <div>
                  <h6 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
                    Must Have ANY
                  </h6>
                  <SearchableMultiSelect
                    options={roleOptions}
                    selected={catPrerequisiteRoleIdsAny}
                    onChange={onCatPrerequisiteRoleIdsAnyChange}
                    placeholder="Search optional roles…"
                    componentId="cat-prerequisite-role-ids-any"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
