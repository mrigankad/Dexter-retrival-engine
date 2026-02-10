import { useEffect } from 'react';
import { useDocumentStore } from '@/stores/documentStore';
import { useChatStore } from '@/stores/chatStore';
import {
    DocumentIcon,
    CheckIcon,
    CircleStackIcon,
    FunnelIcon
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

export function KnowledgeScopeSelector() {
    const { documents, fetchDocuments, isLoading } = useDocumentStore();
    const {
        selectedDocumentIds,
        toggleDocumentSelection,
        setSelectedDocumentIds
    } = useChatStore();

    useEffect(() => {
        fetchDocuments();
    }, [fetchDocuments]);

    const handleSelectAll = () => {
        setSelectedDocumentIds(documents.map(d => d.id));
    };

    const handleDeselectAll = () => {
        setSelectedDocumentIds([]);
    };

    const allSelected = documents.length > 0 && selectedDocumentIds.length === documents.length;

    return (
        <div className="flex flex-col h-full bg-dark-900 border-l border-dark-800 w-72">
            <div className="p-4 border-b border-dark-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <CircleStackIcon className="w-5 h-5 text-nvidia" />
                    <h3 className="font-semibold text-white">Knowledge Scope</h3>
                </div>
                <div className="flex items-center gap-1">
                    <span className="text-xs bg-dark-800 text-dark-400 px-2 py-0.5 rounded-full">
                        {selectedDocumentIds.length}
                    </span>
                </div>
            </div>

            <div className="p-3 space-y-3 flex-1 overflow-y-auto custom-scrollbar">
                {/* Controls */}
                <div className="flex items-center justify-between px-1">
                    <button
                        onClick={allSelected ? handleDeselectAll : handleSelectAll}
                        className="text-xs text-nvidia hover:text-nvidia-light transition-colors font-medium"
                    >
                        {allSelected ? 'Deselect All' : 'Select All'}
                    </button>
                    <div className="text-[10px] text-dark-500 uppercase tracking-wider font-bold">
                        {documents.length} Total
                    </div>
                </div>

                {isLoading && documents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 text-dark-500">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nvidia mb-3" />
                        <p className="text-sm">Loading sources...</p>
                    </div>
                ) : documents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 text-center px-4">
                        <DocumentIcon className="w-10 h-10 text-dark-600 mb-2" />
                        <p className="text-sm text-dark-500">No documents uploaded yet.</p>
                        <a href="/documents" className="text-xs text-nvidia mt-2 hover:underline">Go to Library</a>
                    </div>
                ) : (
                    <div className="space-y-1">
                        <AnimatePresence mode="popLayout">
                            {documents.map((doc) => {
                                const isSelected = selectedDocumentIds.includes(doc.id);
                                return (
                                    <motion.button
                                        key={doc.id}
                                        initial={{ opacity: 0, y: 5 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        onClick={() => toggleDocumentSelection(doc.id)}
                                        className={clsx(
                                            "w-full flex items-center gap-3 p-2.5 rounded-xl transition-all text-left group border",
                                            isSelected
                                                ? "bg-nvidia/10 border-nvidia/30 text-white"
                                                : "bg-dark-800/50 border-transparent text-dark-400 hover:bg-dark-800 hover:text-dark-200"
                                        )}
                                    >
                                        <div className={clsx(
                                            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                                            isSelected ? "bg-nvidia text-dark-950" : "bg-dark-700 text-dark-500 group-hover:bg-dark-600"
                                        )}>
                                            {isSelected ? <CheckIcon className="w-5 h-5 font-bold" /> : <DocumentIcon className="w-4 h-4" />}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium truncate leading-tight">
                                                {doc.filename}
                                            </p>
                                            <p className="text-[10px] text-dark-500 truncate mt-0.5">
                                                {doc.status === 'completed' ? `${doc.chunks_count || 0} chunks • ${doc.total_pages || 0} pages` : 'Processing...'}
                                            </p>
                                        </div>
                                    </motion.button>
                                );
                            })}
                        </AnimatePresence>
                    </div>
                )}
            </div>

            {/* Hint */}
            <div className="p-4 border-t border-dark-800 bg-dark-950/50">
                <div className="flex items-start gap-2">
                    <FunnelIcon className="w-4 h-4 text-dark-500 mt-0.5" />
                    <p className="text-[10px] text-dark-500 leading-relaxed">
                        Query results are filtered by selected documents. Deselect all to search the entire global knowledge base.
                    </p>
                </div>
            </div>
        </div>
    );
}
