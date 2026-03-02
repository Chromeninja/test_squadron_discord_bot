/** Category delete confirmation modal. */

import type { TicketCategory } from '../../api/endpoints';
import { Button, Modal, ModalFooter } from '../../components/ui';

interface DeleteCategoryModalProps {
  category: TicketCategory | null;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export default function DeleteCategoryModal({
  category,
  deleting,
  onClose,
  onConfirm,
}: DeleteCategoryModalProps) {
  return (
    <Modal
      open={!!category}
      onClose={onClose}
      title="Delete Category"
      size="sm"
      headerVariant="error"
      footer={
        <ModalFooter>
          <Button variant="secondary" onClick={onClose} disabled={deleting}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={deleting}>
            {deleting ? 'Deleting…' : 'Delete'}
          </Button>
        </ModalFooter>
      }
    >
      <p className="text-gray-300">
        Are you sure you want to delete the category{' '}
        <strong className="text-white">{category?.name}</strong>? Existing
        tickets in this category will not be affected.
      </p>
    </Modal>
  );
}
