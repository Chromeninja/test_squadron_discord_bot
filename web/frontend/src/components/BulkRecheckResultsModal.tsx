import { showError } from '../utils/toast';
import { getStatusLabel } from '../utils/statusHelpers';
import type { BulkRecheckResponse } from '../api/endpoints';
import { Button, Modal } from './ui';

/**
 * Bulk Recheck Results Modal
 *
 * Displays results from bulk user recheck operation following the same
 * pattern as Discord's /verify check command with summary and CSV export.
 *
 * Uses the shared Modal / Button UI components and imports types from
 * the canonical api/endpoints definitions.
 */

interface BulkRecheckResultsProps {
  open: boolean;
  onClose: () => void;
  results: BulkRecheckResponse;
}

export function BulkRecheckResultsModal({ open, onClose, results }: BulkRecheckResultsProps) {

  const downloadCSV = () => {
    if (!results.csv_content || !results.csv_filename) {
      showError('CSV data is not available yet.');
      return;
    }

    try {
      // Decode base64 to bytes
      const binaryString = atob(results.csv_content);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Create blob and download
      const blob = new Blob([bytes], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = results.csv_filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      showError('Failed to download CSV.');
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'main':
      case 'affiliate':
        return '✓';
      case 'non_member':
        return '✗';
      default:
        return '⚠';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'main':
      case 'affiliate':
        return 'text-green-400';
      case 'non_member':
        return 'text-red-400';
      default:
        return 'text-yellow-400';
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <div className="flex items-center gap-3">
          <span className={`text-2xl ${results.success ? 'text-green-400' : 'text-yellow-400'}`}>
            {results.success ? '✓' : '⚠'}
          </span>
          <div>
            <span className="text-xl font-semibold text-white">Bulk Recheck Results</span>
            <p className="text-sm text-gray-400 mt-1">{results.message}</p>
          </div>
        </div>
      }
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <div>
            {results.csv_content && (
              <Button
                variant="primary"
                size="sm"
                onClick={downloadCSV}
                leftIcon={
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                }
              >
                Download CSV
              </Button>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
          {/* Summary Section */}
          {results.summary_text && (
            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
              <pre className="text-sm font-mono whitespace-pre-wrap text-gray-300">
                {results.summary_text}
              </pre>
            </div>
          )}

          {/* Detailed Results Table */}
          {results.results && results.results.length > 0 && (
            <div className="border border-slate-700 rounded-lg overflow-hidden">
              <div className="bg-slate-900 px-4 py-2 font-semibold text-sm text-gray-300 border-b border-slate-700">
                User Details
              </div>
              <div className="divide-y divide-slate-700 max-h-64 overflow-y-auto">
                {results.results.map((result) => (
                  <div
                    key={result.user_id}
                    className="px-4 py-3 flex items-center justify-between hover:bg-slate-900/50 transition-colors"
                  >
                    <div className="flex items-center gap-3 flex-1">
                      <span className={`text-xl ${getStatusColor(result.status)}`}>
                        {getStatusIcon(result.status)}
                      </span>
                      <div className="flex-1">
                        <div className="font-medium text-sm text-gray-200">
                          User ID: {result.user_id}
                        </div>
                        <div className="text-xs text-gray-400">
                          {getStatusLabel(result.status)}
                        </div>
                      </div>
                    </div>
                    {result.roles_updated > 0 && (
                      <div className="text-xs bg-blue-900/30 text-blue-300 px-2 py-1 rounded">
                        {result.roles_updated} role{result.roles_updated !== 1 ? 's' : ''} updated
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Errors Section */}
          {results.errors && results.errors.length > 0 && (
            <div className="border border-red-900/50 rounded-lg overflow-hidden">
              <div className="bg-red-900/20 px-4 py-2 font-semibold text-sm text-red-300 border-b border-red-900/50">
                Errors ({results.errors.length})
              </div>
              <div className="divide-y divide-red-900/30">
                {results.errors.map((error, index) => (
                  <div
                    key={`${error.user_id}-${index}`}
                    className="px-4 py-3 hover:bg-red-900/10 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <span className="text-red-400 text-xl">✗</span>
                      <div className="flex-1">
                        <div className="font-medium text-sm text-gray-200">
                          User ID: {error.user_id}
                        </div>
                        <div className="text-xs text-gray-400 mt-1">
                          {error.error}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
      </div>
    </Modal>
  );
}
