import api from './api';
import type { ChatResponse, ChatRequest, Document, UploadResponse, AuthTokens, LoginRequest, HealthStatus } from '@/types';

// =====================
// Chat Service
// =====================
export const chatService = {
    // Non-streaming chat
    async send(request: ChatRequest): Promise<ChatResponse> {
        const response = await api.post<ChatResponse>('/chat', {
            ...request,
            stream: false,
        });
        return response.data;
    },

    // Get chat history
    async getHistory(sessionId: string) {
        const response = await api.get(`/chat/history/${sessionId}`);
        return response.data;
    },

    // Clear chat history
    async clearHistory(sessionId: string) {
        const response = await api.delete(`/chat/history/${sessionId}`);
        return response.data;
    },
};

// =====================
// Document Service
// =====================
export const documentService = {
    // Upload document
    async upload(file: File): Promise<UploadResponse> {
        const formData = new FormData();
        formData.append('file', file);

        const response = await api.post<UploadResponse>('/ingest', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        });
        return response.data;
    },

    // List documents
    async list(): Promise<Document[]> {
        const response = await api.get<{ documents: Document[] }>('/documents');
        return response.data.documents || [];
    },

    // Get document status
    async getStatus(documentId: string): Promise<Document> {
        const response = await api.get<Document>(`/documents/${documentId}`);
        return response.data;
    },

    // Delete document
    async delete(documentId: string) {
        const response = await api.delete(`/documents/${documentId}`);
        return response.data;
    },
};

// =====================
// Auth Service
// =====================
export const authService = {
    // Login
    async login(credentials: LoginRequest): Promise<AuthTokens> {
        const response = await api.post<AuthTokens>('/auth/login', credentials);
        return response.data;
    },

    // Register
    async register(data: { username: string; email: string; password: string }): Promise<AuthTokens> {
        const response = await api.post<AuthTokens>('/auth/register', data);
        return response.data;
    },

    // Refresh token
    async refresh(refreshToken: string): Promise<AuthTokens> {
        const response = await api.post<AuthTokens>('/auth/refresh', { refresh_token: refreshToken });
        return response.data;
    },
};

// =====================
// Health Service
// =====================
export const healthService = {
    // Get health status
    async check(): Promise<HealthStatus> {
        const response = await api.get<HealthStatus>('/health');
        return response.data;
    },

    // Get API info
    async info() {
        const response = await api.get('/');
        return response.data;
    },
};
