import { motion, AnimatePresence } from 'framer-motion';
import { XMarkIcon, DocumentTextIcon, BookOpenIcon, TableCellsIcon, PhotoIcon } from '@heroicons/react/24/outline';
import type { Source } from '@/types';
import clsx from 'clsx';
import { openDocumentFile } from '@/utils/fileUrl';

interface SourcePanelProps {
    sources: Source[];
    isOpen: boolean;
    onClose: () => void;
}

export function SourcePanel({ sources, isOpen, onClose }: SourcePanelProps) {
    return (
        <AnimatePresence>
            {isOpen && (
                <motion.div
                    initial={{ width: 0, opacity: 0 }}
                    animate={{ width: 380, opacity: 1 }}
                    exit={{ width: 0, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    className="h-full border-l border-dark-700 bg-dark-900/80 backdrop-blur-lg overflow-hidden"
                >
                    <div className="w-[380px] h-full flex flex-col">
                        {/* Header */}
                        <div className="flex items-center justify-between p-4 border-b border-dark-700">
                            <div className="flex items-center gap-2">
                                <DocumentTextIcon className="w-5 h-5 text-nvidia" />
                                <h3 className="font-semibold text-white">Sources</h3>
                                <span className="px-2 py-0.5 rounded-full bg-nvidia/20 text-nvidia text-xs">
                                    {sources.length}
                                </span>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-1.5 rounded-lg text-dark-400 hover:text-white hover:bg-dark-800 transition-colors"
                            >
                                <XMarkIcon className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Sources List */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-3">
                            {sources.map((source, index) => (
                                <SourceCard key={index} source={source} index={index + 1} />
                            ))}
                        </div>

                        {/* Footer */}
                        <div className="p-4 border-t border-dark-700">
                            <p className="text-xs text-dark-500 text-center">
                                Click on page numbers to navigate to source
                            </p>
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
    const hasPage = source.page !== 'N/A' && source.page !== null;
    const relevancePercent = Math.round(source.score * 100);
    const rerankPercent = source.rerank_score ? Math.round(source.rerank_score * 100) : null;

    const getContentTypeIcon = () => {
        if (source.content_type?.includes('table')) return <TableCellsIcon className="w-4 h-4 text-nvidia" />;
        if (source.content_type?.includes('graphic') || source.content_type?.includes('asset')) return <PhotoIcon className="w-4 h-4 text-nvidia" />;
        return <DocumentTextIcon className="w-4 h-4 text-nvidia" />;
    };

    const handleSourceClick = () => {
        if (source.document_id) {
            openDocumentFile(source.document_id);
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05 }}
            onClick={handleSourceClick}
            className="p-4 rounded-xl glass hover:border-nvidia/50 transition-all duration-200 cursor-pointer group"
        >
            {/* Header */}
            <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-lg bg-nvidia/20 flex items-center justify-center text-nvidia text-xs font-bold">
                        {index}
                    </div>
                    <span className="text-sm font-medium text-white truncate max-w-[180px]" title={source.source}>
                        {source.source.split('.pdf')[0]}
                    </span>
                </div>

                {/* Content Type Badge */}
                {source.content_type && source.content_type !== 'text' && (
                    <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-nvidia/10 text-[10px] text-nvidia font-bold uppercase tracking-wider">
                        {getContentTypeIcon()}
                        {source.content_type.split('_').pop()}
                    </div>
                )}
            </div>

            {/* Relevance & Rerank Scores */}
            <div className="flex flex-col gap-2 mb-3">
                <div className="flex items-center justify-between">
                    <span className="text-[10px] text-dark-500 uppercase font-semibold">Semantic Match</span>
                    <div className="flex items-center gap-1.5">
                        <div className="w-16 h-1 rounded-full bg-dark-700 overflow-hidden">
                            <div
                                className={clsx(
                                    "h-full rounded-full transition-all",
                                    relevancePercent >= 70 ? "bg-green-500" :
                                        relevancePercent >= 50 ? "bg-yellow-500" : "bg-orange-500"
                                )}
                                style={{ width: `${relevancePercent}%` }}
                            />
                        </div>
                        <span className="text-[10px] text-dark-300 font-mono">{relevancePercent}%</span>
                    </div>
                </div>

                {rerankPercent !== null && (
                    <div className="flex items-center justify-between">
                        <span className="text-[10px] text-nvidia uppercase font-bold">NVIDIA Rerank</span>
                        <div className="flex items-center gap-1.5">
                            <div className="w-16 h-1 rounded-full bg-nvidia/20 overflow-hidden">
                                <div
                                    className="h-full rounded-full bg-nvidia transition-all"
                                    style={{ width: `${rerankPercent}%` }}
                                />
                            </div>
                            <span className="text-[10px] text-nvidia font-bold font-mono">{rerankPercent}%</span>
                        </div>
                    </div>
                )}
            </div>

            {/* Page Info */}
            {hasPage && (
                <div className="flex items-center gap-2 mb-2">
                    <BookOpenIcon className="w-4 h-4 text-nvidia" />
                    <span className="text-sm text-dark-300">
                        Page <span className="text-nvidia font-semibold">{source.page}</span>
                        <span className="text-dark-500"> of {source.total_pages}</span>
                    </span>
                </div>
            )}

            {/* Chunk Info */}
            <div className="flex items-center gap-4 text-xs text-dark-500">
                <span>Chunk #{source.chunk_index}</span>
                {!hasPage && (
                    <span className="text-yellow-500/70">Page info unavailable</span>
                )}
            </div>

            {/* Hover Indicator */}
            <div className="mt-3 pt-3 border-t border-dark-700/50 opacity-0 group-hover:opacity-100 transition-opacity">
                <p className="text-xs text-dark-400 text-center">
                    {source.document_id ? "View in document →" : "Source file unavailable"}
                </p>
            </div>
        </motion.div>
    );
}
