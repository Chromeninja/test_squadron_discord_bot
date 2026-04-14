/**
 * API client configuration and utilities.
 */

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE || '';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Send cookies with requests
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Unauthorized - redirect to login (but avoid infinite loop if already on auth page)
      if (!window.location.pathname.startsWith('/auth')) {
        const nextPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const loginUrl = `/auth/login?next=${encodeURIComponent(nextPath || '/')}`;
        window.location.href = loginUrl;
      }
    }
    return Promise.reject(error);
  }
);
