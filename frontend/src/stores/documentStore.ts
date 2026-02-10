import { create } from 'zustand';
import type { Document } from '@/types';
import { documentService } from '@/services';
import toast from 'react-hot-toast';

interface DocumentState {
    documents: Document[];
    isLoading: boolean;
    isUploading: boolean;

    // Actions
    fetchDocuments: () => Promise<void>;
    uploadDocuments: (files: File[]) => Promise<void>;
    deleteDocument: (id: string, name: string) => Promise<void>;
}

export const useDocumentStore = create<DocumentState>((set) => ({
    documents: [],
    isLoading: false,
    isUploading: false,

    fetchDocuments: async () => {
        set({ isLoading: true });
        try {
            const docs = await documentService.list();
            set({ documents: docs });
        } catch (error) {
            toast.error('Failed to load documents');
        } finally {
            set({ isLoading: false });
        }
    },

    uploadDocuments: async (files: File[]) => {
        set({ isUploading: true });
        const uploadPromises = files.map(file =>
            documentService.upload(file)
                .then(() => toast.success(`Uploaded ${file.name}`))
                .catch(() => toast.error(`Failed to upload ${file.name}`))
        );

        await Promise.all(uploadPromises);
        set({ isUploading: false });
        // Refresh local list
        const docs = await documentService.list();
        set({ documents: docs });
    },

    deleteDocument: async (id: string, name: string) => {
        if (!confirm(`Are you sure you want to delete ${name}?`)) return;

        try {
            await documentService.delete(id);
            toast.success('Document deleted');
            const docs = await documentService.list();
            set({ documents: docs });
        } catch (error) {
            toast.error('Failed to delete document');
        }
    }
}));
