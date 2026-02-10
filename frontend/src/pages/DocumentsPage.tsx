import { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import {
    CloudArrowUpIcon,
    DocumentIcon,
    TrashIcon,
    CheckCircleIcon,
    ArrowPathIcon,
    ExclamationCircleIcon,
    MagnifyingGlassIcon
} from '@heroicons/react/24/outline';
import { useDocumentStore } from '@/stores/documentStore';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

export function DocumentsPage() {
    const {
        documents,
        isLoading,
        isUploading,
        fetchDocuments,
        uploadDocuments,
        deleteDocument
    } = useDocumentStore();

    const [searchQuery, setSearchQuery] = useState('');

    useEffect(() => {
        fetchDocuments();
    }, []);

    useEffect(() => {
        // Poll for status every 5 seconds if there are processing documents
        const interval = setInterval(() => {
            const hasProcessing = documents.some(doc => doc.status === 'processing');
            if (hasProcessing) {
                fetchDocuments();
            }
        }, 5000);
        return () => clearInterval(interval);
    }, [documents, fetchDocuments]);

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;
        await uploadDocuments(acceptedFiles);
    }, [uploadDocuments]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: {
            'application/pdf': ['.pdf'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
            'text/plain': ['.txt']
        },
        multiple: true
    });

    const filteredDocuments = documents.filter(doc =>
        doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="h-full flex flex-col p-6 space-y-6 overflow-y-auto bg-dark-950">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-white">Documents</h1>
                    <p className="text-dark-400 text-sm">Manage your knowledge base</p>
                </div>

                <div className="relative">
                    <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
                    <input
                        type="text"
                        placeholder="Search documents..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-10 pr-4 py-2 bg-dark-800 border border-dark-700 rounded-xl text-white focus:outline-none focus:border-nvidia/50 transition-colors w-full md:w-64"
                    />
                </div>
            </div>

            {/* Upload Area */}
            <div
                {...getRootProps()}
                className={clsx(
                    "border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer",
                    isDragActive ? "border-nvidia bg-nvidia/10" : "border-dark-700 hover:border-dark-600 bg-dark-800/50"
                )}
            >
                <input {...getInputProps()} />
                <div className="flex flex-col items-center">
                    <div className="w-16 h-16 rounded-full bg-dark-700 flex items-center justify-center mb-4">
                        {isUploading ? (
                            <ArrowPathIcon className="w-8 h-8 text-nvidia animate-spin" />
                        ) : (
                            <CloudArrowUpIcon className="w-8 h-8 text-dark-400 group-hover:text-nvidia transition-colors" />
                        )}
                    </div>
                    <h3 className="text-lg font-semibold text-white">
                        {isUploading ? 'Uploading documents...' : 'Click or drag files to upload'}
                    </h3>
                    <p className="text-dark-500 text-sm mt-1">
                        Support for PDF, DOCX and TXT files (Max 50MB)
                    </p>
                </div>
            </div>

            {/* Document List */}
            <div className="bg-dark-900/50 rounded-2xl border border-dark-700 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="border-b border-dark-700 bg-dark-800/50">
                                <th className="px-6 py-4 text-xs font-semibold text-dark-400 uppercase tracking-wider">Document</th>
                                <th className="px-6 py-4 text-xs font-semibold text-dark-400 uppercase tracking-wider">Status</th>
                                <th className="px-6 py-4 text-xs font-semibold text-dark-400 uppercase tracking-wider">Details</th>
                                <th className="px-6 py-4 text-xs font-semibold text-dark-400 uppercase tracking-wider">Uploaded</th>
                                <th className="px-6 py-4 text-xs font-semibold text-dark-400 uppercase tracking-wider text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-dark-800">
                            <AnimatePresence mode="popLayout">
                                {isLoading ? (
                                    <tr>
                                        <td colSpan={5} className="px-6 py-12 text-center text-dark-500">
                                            <ArrowPathIcon className="w-10 h-10 animate-spin mx-auto mb-2 opacity-50" />
                                            Loading documents...
                                        </td>
                                    </tr>
                                ) : filteredDocuments.length === 0 ? (
                                    <tr>
                                        <td colSpan={5} className="px-6 py-12 text-center text-dark-500">
                                            <DocumentIcon className="w-10 h-10 mx-auto mb-2 opacity-50" />
                                            No documents found
                                        </td>
                                    </tr>
                                ) : (
                                    filteredDocuments.map((doc) => (
                                        <motion.tr
                                            key={doc.id}
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            exit={{ opacity: 0 }}
                                            className="hover:bg-dark-800/30 transition-colors"
                                        >
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-10 h-10 rounded-lg bg-dark-700 flex items-center justify-center">
                                                        <DocumentIcon className="w-5 h-5 text-dark-400" />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-white font-medium truncate max-w-[200px]" title={doc.filename}>
                                                            {doc.filename}
                                                        </p>
                                                        <p className="text-xs text-dark-500">ID: {doc.id ? doc.id.split('-')[0] : 'N/A'}...</p>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <StatusBadge status={doc.status} />
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="text-sm text-dark-300">
                                                    {doc.status === 'completed' ? (
                                                        <>
                                                            <p>{doc.chunks_count || 0} chunks</p>
                                                            <p className="text-xs text-dark-500">{doc.total_pages || 0} pages</p>
                                                        </>
                                                    ) : (
                                                        <span className="text-dark-500">-</span>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-sm text-dark-400">
                                                {new Date(doc.uploaded_at).toLocaleDateString()}
                                            </td>
                                            <td className="px-6 py-4 text-right">
                                                <button
                                                    onClick={() => deleteDocument(doc.id, doc.filename)}
                                                    className="p-2 text-dark-500 hover:text-red-500 transition-colors"
                                                >
                                                    <TrashIcon className="w-5 h-5" />
                                                </button>
                                            </td>
                                        </motion.tr>
                                    ))
                                )}
                            </AnimatePresence>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function StatusBadge({ status }: { status: string }) {
    const styles = {
        completed: "bg-green-500/10 text-green-500 border-green-500/20",
        processing: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
        failed: "bg-red-500/10 text-red-500 border-red-500/20",
    };

    const icons = {
        completed: <CheckCircleIcon className="w-4 h-4" />,
        processing: <ArrowPathIcon className="w-4 h-4 animate-spin" />,
        failed: <ExclamationCircleIcon className="w-4 h-4" />,
    };

    const currentStyle = styles[status as keyof typeof styles] || styles.failed;
    const currentIcon = icons[status as keyof typeof icons] || icons.failed;

    return (
        <div className={clsx("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", currentStyle)}>
            {currentIcon}
            <span className="capitalize">{status}</span>
        </div>
    );
}
