/**
 * Example Integration: Using BulkRecheckResultsModal
 * 
 * This shows how to integrate the bulk recheck results modal into
 * your admin users page. Add this code to your existing admin page.
 */

import { useState } from 'react';
import { BulkRecheckResultsModal } from './BulkRecheckResultsModal';
import { apiClient } from '../api/client';
import { handleApiError, showError } from '../utils/toast';

// Example: In your AdminUsersPage component
export function AdminUsersPageExample() {
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [recheckResults, setRecheckResults] = useState(null);
  const [showResultsModal, setShowResultsModal] = useState(false);
  const [isRechecking, setIsRechecking] = useState(false);

  const handleBulkRecheck = async () => {
    if (selectedUsers.length === 0) {
      showError('Please select at least one user to recheck.');
      return;
    }

    setIsRechecking(true);

    try {
      // Call the bulk recheck endpoint
      const response = await apiClient.post('/api/admin/users/bulk-recheck', {
        user_ids: selectedUsers,
      });

      // Store results and show modal
      setRecheckResults(response.data);
      setShowResultsModal(true);

      // Optionally refresh the user list
      // await refetchUsers();

    } catch (error) {
      handleApiError(error, 'Failed to perform bulk recheck. Please try again.');
    } finally {
      setIsRechecking(false);
    }
  };

  return (
    <div>
      {/* Your existing users list UI */}
      <div className="p-4">
        <h1>Admin Users Management</h1>
        
        {/* Example user selection and bulk recheck button */}
        <div className="flex justify-between items-center mb-4">
          <div className="text-sm text-muted-foreground">
            {selectedUsers.length} user{selectedUsers.length !== 1 ? 's' : ''} selected
          </div>
          <button
            onClick={handleBulkRecheck}
            disabled={isRechecking || selectedUsers.length === 0}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {isRechecking ? 'Rechecking...' : 'Bulk Recheck'}
          </button>
        </div>

        {/* Your users table/list here */}
        {/* ... */}
      </div>

      {/* Results Modal */}
      {recheckResults && (
        <BulkRecheckResultsModal
          open={showResultsModal}
          onClose={() => {
            setShowResultsModal(false);
            setRecheckResults(null);
            // Optionally clear selection
            setSelectedUsers([]);
          }}
          results={recheckResults}
        />
      )}
    </div>
  );
}

/**
 * Alternative: Trigger from a context menu or action button
 */
export function UserRowWithRecheckExample({ userId }: { userId: string }) {
  const [recheckResults, setRecheckResults] = useState(null);
  const [showResultsModal, setShowResultsModal] = useState(false);

  const handleSingleRecheck = async () => {
    try {
      const response = await apiClient.post('/api/admin/users/bulk-recheck', {
        user_ids: [userId],
      });

      setRecheckResults(response.data);
      setShowResultsModal(true);
    } catch (error) {
      handleApiError(error, 'Failed to recheck user. Please try again.');
    }
  };

  return (
    <div>
      <button onClick={handleSingleRecheck}>Recheck</button>

      {recheckResults && (
        <BulkRecheckResultsModal
          open={showResultsModal}
          onClose={() => {
            setShowResultsModal(false);
            setRecheckResults(null);
          }}
          results={recheckResults}
        />
      )}
    </div>
  );
}
