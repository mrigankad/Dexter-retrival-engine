/**
 * SourceBadge — Inline source citation badge.
 *
 * Appears during/after streaming with a smooth fade-in.
 * Clickable to open PDF viewer at specific page.
 */

import { motion } from 'framer-motion';
import { DocumentTextIcon, TableCellsIcon, PhotoIcon } from '@heroicons/react/24/solid';
import clsx from 'clsx';
import type { Source } from '@/types';
import { openDocumentFile } from '@/utils/fileUrl';

interface SourceBadgeProps {
    source: Source;
    index: number;
    onClick?: (source: Source) => void;
    compact?: boolean;
}

export function SourceBadge({ source, index, onClick, compact = false }: SourceBadgeProps) {
    const hasPage = source.page !== 'N/A' && source.page !== null && source.page !== undefined;

    const getIcon = () => {
        if (source.content_type?.includes('table')) return <TableCellsIcon className="w-3 h-3" />;
        if (source.content_type?.includes('graphic') || source.content_type?.includes('asset')) return <PhotoIcon className="w-3 h-3" />;
        return <DocumentTextIcon className="w-3 h-3" />;
    };

    const handleClick = () => {
        if (onClick) {
            onClick(source);
        } else if (source.document_id) {
            openDocumentFile(source.document_id);
        }
    };

    if (compact) {
        return (
            <motion.button
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.05, duration: 0.2 }}
                onClick={handleClick}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-nvidia/10 border border-nvidia/20 text-nvidia text-xs font-medium hover:bg-nvidia/20 hover:border-nvidia/40 transition-all duration-200 cursor-pointer group"
                title={`${source.source} — Page ${source.page}`}
            >
                {getIcon()}
                <span>p.{source.page}</span>
            </motion.button>
        );
    }

    return (
        <motion.button
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: index * 0.06, duration: 0.25, ease: 'easeOut' }}
            onClick={handleClick}
            className={clsx(
                "flex items-center gap-2 px-3 py-2 rounded-xl",
                "bg-nvidia/8 border border-nvidia/20",
                "hover:bg-nvidia/15 hover:border-nvidia/40 hover:shadow-sm hover:shadow-nvidia/10",
                "transition-all duration-200 cursor-pointer group"
            )}
            title={`${source.source} — Page ${source.page} — Score: ${Math.round(source.score * 100)}%`}
        >
            <div className="w-6 h-6 rounded-lg bg-nvidia/20 flex items-center justify-center text-nvidia group-hover:bg-nvidia/30 transition-colors">
                {getIcon()}
            </div>

            <div className="flex flex-col items-start text-left min-w-0">
                <span className="text-xs font-medium text-white truncate max-w-[120px]">
                    {source.source.replace('.pdf', '')}
                </span>
                <div className="flex items-center gap-1.5">
                    {hasPage && (
                        <span className="text-[10px] text-nvidia font-semibold">
                            Page {source.page}
                        </span>
                    )}
                    {source.rerank_score != null && (
                        <span className="text-[10px] text-dark-500">
                            · {Math.round(source.rerank_score * 100)}%
                        </span>
                    )}
                </div>
            </div>
        </motion.button>
    );
}

/**
 * SourceBadgeList — Renders a list of source badges with staggered animation.
 */
interface SourceBadgeListProps {
    sources: Source[];
    onSourceClick?: (source: Source) => void;
    compact?: boolean;
}

export function SourceBadgeList({ sources, onSourceClick, compact = false }: SourceBadgeListProps) {
    if (!sources || sources.length === 0) return null;

    // Deduplicate by source + page
    const unique = sources.reduce<Source[]>((acc, s) => {
        const key = `${s.source}_${s.page}_${s.chunk_index}`;
        if (!acc.some((existing) => `${existing.source}_${existing.page}_${existing.chunk_index}` === key)) {
            acc.push(s);
        }
        return acc;
    }, []);

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className={clsx(
                "flex flex-wrap gap-2 mt-3",
                compact && "gap-1.5"
            )}
        >
            {unique.map((source, index) => (
                <SourceBadge
                    key={`${source.source}_${source.page}_${source.chunk_index}`}
                    source={source}
                    index={index}
                    onClick={onSourceClick}
                    compact={compact}
                />
            ))}
        </motion.div>
    );
}
