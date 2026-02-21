/**
 * Trigger a browser download from a Blob response.
 *
 * Eliminates the repeated create-objectURL → click → revoke pattern across
 * export endpoints.
 */
export function triggerBlobDownload(data: BlobPart, filename: string): void {
  const url = window.URL.createObjectURL(new Blob([data]));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

/**
 * Extract a filename from a Content-Disposition header, falling back to
 * `fallback` when the header is missing or un-parseable.
 */
export function extractFilename(
  contentDisposition: string | undefined | null,
  fallback: string,
): string {
  if (!contentDisposition) return fallback;
  const match = contentDisposition.match(/filename[^;=\n]*=(['"]?)([^'"\n;]+)\1/);
  return match?.[2] ?? fallback;
}
