/**
 * File URL utility — builds authenticated URLs for opening documents.
 *
 * Since window.open() cannot send Authorization headers,
 * we append the JWT token as a query parameter.
 */

import { useAuthStore } from '@/stores/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

/**
 * Build an authenticated URL for serving a file via the backend.
 * The backend's /files/{document_id} endpoint accepts a `token` query param.
 */
export function getFileUrl(documentId: string): string {
    const token = useAuthStore.getState().token;
    const base = `${API_BASE_URL}/files/${documentId}`;
    return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

/**
 * Open a document file in a new browser tab with auth.
 */
export function openDocumentFile(documentId: string): void {
    const url = getFileUrl(documentId);
    window.open(url, '_blank');
}
