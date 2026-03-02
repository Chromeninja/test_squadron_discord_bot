/**
 * ChannelAddModal — Select Discord channels to configure for ticketing
 *
 * Displays available text channels that aren't already configured,
 * allows multi-select, and creates default channel configs.
 */

import { useState } from 'react';
import { Button, Modal, ModalFooter } from '../../components/ui';
import SearchableMultiSelect, { type MultiSelectOption } from '../../components/SearchableMultiSelect';

interface ChannelAddModalProps {
  open: boolean;
  onClose: () => void;
  availableChannels: MultiSelectOption[];
  onAdd: (channelIds: string[]) => Promise<void>;
}

export default function ChannelAddModal({
  open,
  onClose,
  availableChannels,
  onAdd,
}: ChannelAddModalProps) {
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);

  const handleAdd = async () => {
    if (selectedChannels.length === 0) return;

    setAdding(true);
    try {
      await onAdd(selectedChannels);
      setSelectedChannels([]);
      onClose();
    } finally {
      setAdding(false);
    }
  };

  const handleClose = () => {
    setSelectedChannels([]);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Add Ticket Channels"
      size="md"
      footer={
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={handleClose}
            disabled={adding}
            className="px-2 py-1 text-xs"
          >
            Cancel
          </Button>
          <Button
            onClick={handleAdd}
            loading={adding}
            disabled={selectedChannels.length === 0}
            className="px-3 py-1 text-xs"
          >
            {adding
              ? 'Adding…'
              : `Add ${selectedChannels.length || ''}`}
          </Button>
        </ModalFooter>
      }
    >
      <div className="min-h-[300px] flex flex-col">
        <div className="space-y-1">
          <SearchableMultiSelect
            options={availableChannels}
            selected={selectedChannels}
            onChange={setSelectedChannels}
            placeholder="Search channels..."
            componentId="channel-add-modal"
          />

          {selectedChannels.length > 0 && (
            <p className="text-[11px] text-gray-500 mt-1">
              {selectedChannels.length} channel{selectedChannels.length === 1 ? '' : 's'} selected
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
}
