/**
 * Toast notification utilities for consistent error/success messaging.
 * 
 * Replaces console.error/alert with user-friendly toast notifications.
 */

import toast from 'react-hot-toast';

/**
 * Show a success toast notification.
 */
export function showSuccess(message: string) {
  toast.success(message, {
    duration: 3000,
    position: 'top-right',
  });
}

/**
 * Show an error toast notification.
 */
export function showError(message: string) {
  toast.error(message, {
    duration: 5000,
    position: 'top-right',
  });
}

/**
 * Show an informational toast notification.
 */
export function showInfo(message: string) {
  toast(message, {
    duration: 4000,
    position: 'top-right',
    icon: 'ℹ️',
  });
}

/**
 * Show a loading toast that persists until dismissed.
 * Returns a function to dismiss the toast.
 */
export function showLoading(message: string): () => void {
  const toastId = toast.loading(message, {
    position: 'top-right',
  });
  
  return () => toast.dismiss(toastId);
}

/**
 * Handle API errors with consistent toast messaging.
 * Extracts error message from axios error response if available.
 */
export function handleApiError(error: any, fallbackMessage: string = 'An error occurred') {
  const message = error?.response?.data?.error?.message || error?.message || fallbackMessage;
  showError(message);
}

/**
 * Handle non-Axios response errors with consistent toast messaging.
 */
export function handleResponseError(response: any, fallbackMessage: string = 'An error occurred') {
  const message =
    response?.data?.error?.message ||
    response?.error?.message ||
    response?.statusText ||
    response?.message ||
    fallbackMessage;
  showError(message);
}
