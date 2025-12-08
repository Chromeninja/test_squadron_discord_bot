import { showError } from '../utils/toast';

/**
 * Bulk Recheck Results Modal
 * 
 * Displays results from bulk user recheck operation following the same
 * pattern as Discord's /verify check command with summary and CSV export.
 */

interface BulkRecheckResult {
  user_id: string;
  status: string;
  message: string;
  roles_updated: number;
  diff: Record<string, any>;
}

interface BulkRecheckError {
  user_id: string;
  error: string;
}

interface BulkRecheckResultsProps {
  open: boolean;
  onClose: () => void;
  results: {
    success: boolean;
    message: string;
    total: number;
    successful: number;
    failed: number;
    errors: BulkRecheckError[];
    results: BulkRecheckResult[];
    summary_text: string | null;
    csv_filename?: string | null;
    csv_content?: string | null; // Base64-encoded CSV
  };
}

export function BulkRecheckResultsModal({ open, onClose, results }: BulkRecheckResultsProps) {
  if (!open) return null;

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

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      main: 'Main Member',
      affiliate: 'Affiliate',
      non_member: 'Non-Member',
      unknown: 'Unknown',
      unverified: 'Unverified',
    };
    return labels[status] || status;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-slate-800 rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] overflow-y-auto mx-4 border border-slate-700">
        {/* Header */}
        <div className="sticky top-0 bg-slate-800 border-b border-slate-700 px-6 py-4 z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className={`text-2xl ${results.success ? 'text-green-400' : 'text-yellow-400'}`}>
                {results.success ? '✓' : '⚠'}
              </span>
              <div>
                <h2 className="text-xl font-semibold text-white">Bulk Recheck Results</h2>
                <p className="text-sm text-gray-400 mt-1">{results.message}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
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

          {/* CSV Export Button */}
          {results.csv_content && (
            <div className="flex justify-between items-center pt-4 border-t border-slate-700">
              <p className="text-sm text-gray-400">
                Download complete results with all fields
              </p>
              <button
                onClick={downloadCSV}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download CSV
              </button>
            </div>
          )}

          {/* Close Button */}
          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
