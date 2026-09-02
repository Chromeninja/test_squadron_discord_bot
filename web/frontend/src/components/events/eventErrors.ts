/**
 * Extract a human-readable message from an Axios-style API error.
 *
 * Falls back to the provided default when no structured detail is available.
 */
export function extractEventError(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }
  return fallback;
}
