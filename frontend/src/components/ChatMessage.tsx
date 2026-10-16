/**
 * ChatMessage — Production message bubble with streaming support.
 *
 * Features:
 * - Status-aware rendering (thinking, streaming, done, error)
 * - Streaming cursor that disappears on completion
 * - Live source badges appearing during streaming
 * - Retry button on error with partial content preservation
 * - Markdown rendering with styled components
 * - Safety verification badge
 */

import { memo, useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from 'framer-motion';
import {
    UserCircleIcon,
    SparklesIcon,
    DocumentTextIcon,
    ShieldCheckIcon,
    ExclamationTriangleIcon,
    TableCellsIcon,
    ArrowPathIcon,
} from '@heroicons/react/24/solid';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check, Terminal } from 'lucide-react';
import clsx from 'clsx';
import type { Message, Source } from '@/types';
import { StreamingCursor, ThinkingIndicator } from './chat/StreamingCursor';
import { DataBlocks } from './chat/DataBlocks';
import { SourceBadgeList } from './chat/SourceBadge';
import { openDocumentFile } from '@/utils/fileUrl';
import QualityBadge from './QualityBadge';
import { useChatStore } from '@/stores/chatStore';

interface ChatMessageProps {
    message: Message;
    onShowSources?: (sources: Source[]) => void;
    onRetry?: (messageId: string) => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const preprocessMarkdown = (text: string) => {
    if (!text) return '';

    let processed = text;

    // --- 0. Aggressive Formatting Fixes for "Jammed" Text ---
    // These must be careful not to break table structures (containing '|')

    // Fix: Horizontal rules jammed with text. Exclude pipes to avoid breaking table delimiters.
    processed = processed.replace(/([^\n\-\|])\s*(-{3,})\s*([^\n\-\|])/g, '$1\n\n$2\n\n$3');

    // Fix: Headers jammed with text. Exclude pipes to avoid breaking table rows.
    processed = processed.replace(/([^\n\|])\s+(#{1,6}\s)/g, '$1\n\n$2');

    // Fix: Bullet points jammed with punctuation. Exclude pipes.
    processed = processed.replace(/([.:!?)])\s+([-*]\s)(?![^|\n]*\|)/g, '$1\n$2');

    // Fix: Numbered lists jammed with punctuation. Exclude pipes.
    processed = processed.replace(/([.:!?)])\s+(\d+\.\s)(?![^|\n]*\|)/g, '$1\n$2');

    // 1. Fix double pipes '||' often used by models as row separators
    processed = processed.replace(/\|\|/g, '|\n|');

    // 2. Ensure table delimiter row starts on a newline if jammed with header text
    processed = processed.replace(/([^\n])\s*(\|[ \t]*:?-{2,}:?[ \t]*\|)/g, '$1\n$2');

    const lines = processed.split('\n');
    const resultLines: string[] = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const nextLine = lines[i + 1] || '';

        // Robust delimiter check: starts with pipe (or near) and contains 2+ dashes
        const isNextDelimiter = /^\s*\|[ \t]*:?-{2,}:?[ \t]*\|/.test(nextLine) ||
            /^\s*\|.*[-]{2,}.*\|/.test(nextLine);

        if (isNextDelimiter) {
            // "line" is potentially the header row.
            // Check if it's jammed with text before the first pipe.
            let headerRow = line;
            const firstPipeIdx = line.indexOf('|');

            if (firstPipeIdx > 0) {
                const preText = line.substring(0, firstPipeIdx).trim();
                // Heuristic: non-empty text before pipe and not a pipe itself -> split it
                if (preText.length > 0 && !preText.includes('|')) {
                    resultLines.push(preText);
                    resultLines.push(''); // Blank line required by Markdown for the table to start
                    headerRow = line.substring(firstPipeIdx);
                }
            }

            // Fix: Ensure delimiter row matches header column count
            const pipeCount = (headerRow.match(/\|/g) || []).length;

            if (pipeCount >= 2) {
                // Construct a generic delimiter row if the original looks broken
                // or just to ensure compatibility. Columns = pipeCount - 1
                const newDelimiter = '|' + ' --- |'.repeat(pipeCount - 1);

                resultLines.push(headerRow);
                resultLines.push(newDelimiter);

                // Skip the original delimiter line
                i++;
                continue;
            }
        }

        resultLines.push(line);
    }
    return resultLines.join('\n');
};

export const ChatMessage = memo(function ChatMessage({
    message,
    onShowSources,
    onRetry,
}: ChatMessageProps) {
    const isUser = message.role === 'user';
    const isThinking = message.status === 'thinking';
    const isStreaming = message.status === 'streaming';
    const isError = message.status === 'error';
    const isDone = message.status === 'done';

    const addMetadata = useChatStore(s => s.addMetadata);
    const [isEvaluating, setIsEvaluating] = useState(false);

    // Polling for Evaluation Scores
    useEffect(() => {
        if (!isUser && isDone && message.backend_id && !message.evaluation && !isEvaluating) {
            let pollCount = 0;
            const maxPolls = 10;
            const pollInterval = 3000; // 3 seconds

            const fetchEval = async () => {
                try {
                    setIsEvaluating(true);
                    const resp = await fetch(`${API_BASE_URL}/evaluations/${message.backend_id}`);
                    if (resp.ok) {
                        const data = await resp.json();
                        if (data.status === 'completed' && data.scores) {
                            addMetadata(message.id, { evaluation: data.scores });
                            setIsEvaluating(false);
                            return true;
                        }
                    }
                } catch (e) {
                    console.error("Failed to fetch evaluation", e);
                }
                return false;
            };

            const poll = async () => {
                const success = await fetchEval();
                if (!success && pollCount < maxPolls) {
                    pollCount++;
                    setTimeout(poll, pollInterval);
                } else {
                    setIsEvaluating(false);
                }
            };

            // Start polling after a short delay to allow backend worker to start
            const timeoutId = setTimeout(poll, 2000);
            return () => clearTimeout(timeoutId);
        }
    }, [isUser, isDone, message.backend_id, message.evaluation, message.id, addMetadata, isEvaluating]);

    // Parse reasoning content (for thinking models like DeepSeek-R1)
    let reasoningContent = '';
    let mainContent = message.content;

    if (message.content && !isUser) {
        const thinkMatch = message.content.match(/<think>([\s\S]*?)(?:<\/think>|$)/);
        if (thinkMatch) {
            reasoningContent = thinkMatch[1].trim();
            mainContent = message.content.replace(/<think>[\s\S]*?(?:<\/think>|$)/, '').trim();
        }
    }

    const handleRetry = useCallback(() => {
        onRetry?.(message.id);
    }, [onRetry, message.id]);

    return (
        <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className={clsx(
                "flex gap-4 group",
                isUser ? "justify-end" : "justify-start"
            )}
        >
            {/* Assistant Avatar */}
            {!isUser && (
                <div className="flex-shrink-0 pt-1">
                    <div className={clsx(
                        "w-10 h-10 rounded-xl flex items-center justify-center shadow-lg transition-all duration-300",
                        isStreaming || isThinking
                            ? "bg-gradient-to-br from-nvidia to-primary-500 animate-pulse-glow"
                            : isError
                                ? "bg-gradient-to-br from-red-500 to-red-700"
                                : "bg-gradient-to-br from-nvidia to-primary-500"
                    )}>
                        <SparklesIcon className="w-5 h-5 text-white" />
                    </div>
                </div>
            )}

            {/* Message Bubble */}
            <div className={clsx(
                "max-w-[85%] rounded-2xl relative",
                isUser
                    ? "bg-nvidia text-white rounded-br-md px-5 py-4"
                    : clsx(
                        "glass rounded-bl-md px-6 py-5",
                        isError && "border-red-500/30"
                    )
            )}>
                {/* Content */}
                {isUser ? (
                    <p className="text-white whitespace-pre-wrap leading-relaxed">{message.content}</p>
                ) : (
                    <div className="markdown-content">
                        {/* Thinking state — waiting for first token */}
                        {isThinking && <ThinkingIndicator label={message.stage?.label} />}

                        {/* Reasoning Block for Thinking Models */}
                        {reasoningContent && (
                            <details className="mb-4 group/reasoning">
                                <summary className="flex items-center gap-2 text-xs font-semibold text-amber-500 cursor-pointer select-none hover:text-amber-400 transition-colors">
                                    <span className="p-1 rounded bg-amber-500/10 group-hover/reasoning:bg-amber-500/20 transition-colors">
                                        <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                                    </span>
                                    Reasoning Process
                                </summary>
                                <div className="mt-3 pl-4 border-l-2 border-amber-500/20 text-xs text-dark-300 font-mono whitespace-pre-wrap leading-relaxed opacity-80">
                                    {reasoningContent}
                                    {isStreaming && !message.content.includes('</think>') && (
                                        <span className="inline-block w-1.5 h-3 ml-1 bg-amber-500/50 animate-pulse" />
                                    )}
                                </div>
                            </details>
                        )}

                        {/* Streaming / Done content */}
                        {(isStreaming || isDone || isError) && (
                            <>
                                {mainContent && (
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={markdownComponents}
                                    >
                                        {preprocessMarkdown(mainContent)}
                                    </ReactMarkdown>
                                )}

                                {/* Streaming cursor */}
                                <AnimatePresence>
                                    <StreamingCursor
                                        isVisible={isStreaming && (!message.content.includes('<think>') || message.content.includes('</think>'))}
                                    />
                                </AnimatePresence>
                            </>
                        )}

                        {/* Structured data blocks (tables / charts from data.query) */}
                        {!isUser && message.blocks && message.blocks.length > 0 && (
                            <DataBlocks blocks={message.blocks} />
                        )}

                        {/* Answer confidence + route (from the engine's done/metadata events) */}
                        {isDone && !isUser && message.confidence && (
                            <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-medium">
                                <span
                                    className={
                                        'px-2 py-0.5 rounded-full border ' +
                                        (message.confidence === 'high'
                                            ? 'border-green-500/40 text-green-400 bg-green-500/10'
                                            : message.confidence === 'medium'
                                                ? 'border-amber-500/40 text-amber-400 bg-amber-500/10'
                                                : 'border-red-500/40 text-red-400 bg-red-500/10')
                                    }
                                    title={message.trace_id ? `trace ${message.trace_id}` : undefined}
                                >
                                    {message.confidence.toUpperCase()} CONFIDENCE
                                </span>
                                {message.intent && (
                                    <span className="px-2 py-0.5 rounded-full border border-dark-600 text-dark-300">
                                        {message.intent.toLowerCase()}
                                    </span>
                                )}
                                {typeof message.latency_ms === 'number' && (
                                    <span className="text-dark-500">{(message.latency_ms / 1000).toFixed(1)}s</span>
                                )}
                                {message.warnings?.map((w, i) => (
                                    <span key={i} className="text-amber-500/80">{w}</span>
                                ))}
                            </div>
                        )}

                        {/* Evaluation Badges */}
                        {isDone && !isUser && (message.evaluation || isEvaluating) && (
                            <div className="mt-4 pt-4 border-t border-dark-600/50 flex flex-wrap gap-2 items-center">
                                {message.evaluation ? (
                                    <>
                                        <div className="flex items-center gap-1.5 text-[10px] text-dark-400 font-medium mr-1">
                                            <ShieldCheckIcon className="w-3.5 h-3.5 text-green-500/70" />
                                            RAGAS VERIFIED
                                        </div>
                                        <QualityBadge label="Faithfulness" value={message.evaluation.faithfulness || 0} />
                                        <QualityBadge label="Relevance" value={message.evaluation.relevance || 0} />
                                    </>
                                ) : (
                                    <div className="flex items-center gap-2 text-[10px] text-dark-400 animate-pulse">
                                        <ArrowPathIcon className="w-3 h-3 animate-spin" />
                                        CALCULATING QUALITY SCORES...
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Error state */}
                        {isError && (
                            <motion.div
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="mt-4 flex items-center gap-3 p-3 rounded-xl bg-red-500/10 border border-red-500/20"
                            >
                                <ExclamationTriangleIcon className="w-5 h-5 text-red-400 flex-shrink-0" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm text-red-300">
                                        {message.error || 'Something went wrong'}
                                    </p>
                                    {message.content && (
                                        <p className="text-xs text-red-400/70 mt-1">
                                            Partial response preserved above
                                        </p>
                                    )}
                                </div>
                                <button
                                    onClick={handleRetry}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-300 text-sm font-medium transition-all duration-200"
                                >
                                    <ArrowPathIcon className="w-4 h-4" />
                                    Retry
                                </button>
                            </motion.div>
                        )}
                    </div>
                )}

                {/* Source Badges — appear live during streaming */}
                {!isUser && message.sources && message.sources.length > 0 && (
                    <SourceBadgeList
                        sources={message.sources}
                        onSourceClick={(source) => {
                            if (onShowSources) {
                                onShowSources(message.sources!);
                            } else if (source.document_id) {
                                openDocumentFile(source.document_id);
                            }
                        }}
                        compact={isStreaming}
                    />
                )}

                {/* Bottom Actions Bar */}
                {!isUser && isDone && (
                    <div className="mt-4 flex items-center justify-between">
                        {/* Sources Button */}
                        {message.sources && message.sources.length > 0 ? (
                            <button
                                onClick={() => onShowSources?.(message.sources!)}
                                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-nvidia/10 border border-nvidia/30 text-sm text-nvidia hover:bg-nvidia/20 hover:border-nvidia/50 transition-all duration-200 group/btn"
                            >
                                <DocumentTextIcon className="w-4 h-4 group-hover/btn:scale-110 transition-transform" />
                                <span className="font-medium">{message.sources.length} Sources</span>
                            </button>
                        ) : <div />}

                    </div>
                )}
            </div>

            {/* User Avatar */}
            {isUser && (
                <div className="flex-shrink-0 pt-1">
                    <div className="w-10 h-10 rounded-xl bg-dark-700 flex items-center justify-center border border-dark-600">
                        <UserCircleIcon className="w-6 h-6 text-dark-400" />
                    </div>
                </div>
            )}
        </motion.div >
    );
});

// ── Code Block Component ────────────────────────────────────

const CodeBlock = ({ language, value }: { language: string; value: string }) => {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="group relative my-6 rounded-xl overflow-hidden border border-dark-600 bg-dark-900 shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 bg-dark-800 border-b border-dark-600">
                <div className="flex items-center gap-2">
                    <Terminal className="w-3.5 h-3.5 text-nvidia" />
                    <span className="text-[10px] font-bold text-dark-300 uppercase tracking-widest">
                        {language || 'code'}
                    </span>
                </div>
                <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-dark-700 transition-colors text-dark-400 hover:text-white"
                >
                    {copied ? (
                        <>
                            <Check className="w-3.5 h-3.5 text-green-500" />
                            <span className="text-[10px] font-medium text-green-500">Copied!</span>
                        </>
                    ) : (
                        <>
                            <Copy className="w-3.5 h-3.5" />
                            <span className="text-[10px] font-medium">Copy code</span>
                        </>
                    )}
                </button>
            </div>

            {/* Content */}
            <div className="p-0 overflow-x-auto">
                <SyntaxHighlighter
                    language={language || 'text'}
                    style={vscDarkPlus}
                    customStyle={{
                        margin: 0,
                        padding: '1.25rem',
                        background: 'transparent',
                        fontSize: '13px',
                        lineHeight: '1.6',
                    }}
                    codeTagProps={{
                        style: { fontFamily: '"JetBrains Mono", Menlo, Monaco, Consolas, "Courier New", monospace' }
                    }}
                >
                    {value}
                </SyntaxHighlighter>
            </div>
        </div>
    );
};


// ── Markdown Component Overrides ────────────────────────────

const markdownComponents = {
    p: ({ children }: { children?: React.ReactNode }) => (
        <p className="mb-4 last:mb-0 text-dark-100 leading-relaxed whitespace-pre-wrap">
            {children}
        </p>
    ),

    h1: ({ children }: { children?: React.ReactNode }) => (
        <h1 className="text-xl font-bold text-white mb-4 mt-6 first:mt-0 pb-2 border-b border-dark-600">
            {children}
        </h1>
    ),
    h2: ({ children }: { children?: React.ReactNode }) => (
        <h2 className="text-lg font-semibold text-white mb-3 mt-5 first:mt-0 flex items-center gap-2">
            <span className="w-1 h-5 bg-nvidia rounded-full"></span>
            {children}
        </h2>
    ),
    h3: ({ children }: { children?: React.ReactNode }) => (
        <h3 className="text-base font-semibold text-dark-100 mb-2 mt-4 first:mt-0">
            {children}
        </h3>
    ),

    strong: ({ children }: { children?: React.ReactNode }) => (
        <strong className="text-nvidia font-semibold">{children}</strong>
    ),
    em: ({ children }: { children?: React.ReactNode }) => (
        <em className="text-dark-200 italic">{children}</em>
    ),

    ul: ({ children }: { children?: React.ReactNode }) => (
        <ul className="mb-4 ml-1 space-y-2">
            {children}
        </ul>
    ),
    ol: ({ children }: { children?: React.ReactNode }) => (
        <ol className="mb-4 ml-1 space-y-2 list-decimal list-inside">
            {children}
        </ol>
    ),
    li: ({ children }: { children?: React.ReactNode }) => (
        <li className="flex items-start gap-3 text-dark-100">
            <span className="flex-shrink-0 w-2 h-2 rounded-full bg-nvidia mt-2"></span>
            <span className="flex-1">{children}</span>
        </li>
    ),

    table: ({ children }: { children?: React.ReactNode }) => (
        <div className="my-6 overflow-hidden rounded-xl border border-dark-600 bg-dark-800/50 shadow-sm">
            <div className="flex items-center gap-2 px-4 py-2 bg-dark-700/50 border-b border-dark-600">
                <TableCellsIcon className="w-4 h-4 text-nvidia" />
                <span className="text-[11px] font-bold text-nvidia uppercase tracking-wider">
                    Data Table
                </span>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left border-collapse">
                    {children}
                </table>
            </div>
        </div>
    ),
    thead: ({ children }: { children?: React.ReactNode }) => (
        <thead className="bg-dark-700/30 text-xs uppercase text-dark-300 font-semibold tracking-wider">
            {children}
        </thead>
    ),
    tbody: ({ children }: { children?: React.ReactNode }) => (
        <tbody className="divide-y divide-dark-700/50 text-dark-200">
            {children}
        </tbody>
    ),
    tr: ({ children }: { children?: React.ReactNode }) => (
        <tr className="hover:bg-nvidia/5 transition-colors group">
            {children}
        </tr>
    ),
    th: ({ children }: { children?: React.ReactNode }) => (
        <th className="px-5 py-3 border-b border-dark-600 first:pl-6 last:pr-6 whitespace-nowrap">
            {children}
        </th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
        <td className="px-5 py-3 first:pl-6 last:pr-6 group-hover:text-dark-100 transition-colors">
            {children}
        </td>
    ),

    blockquote: ({ children }: { children?: React.ReactNode }) => (
        <blockquote className="my-4 pl-4 border-l-4 border-nvidia bg-dark-800/50 py-3 pr-4 rounded-r-lg italic text-dark-300">
            {children}
        </blockquote>
    ),

    hr: () => (
        <hr className="my-6 border-0 h-px bg-gradient-to-r from-transparent via-dark-500 to-transparent" />
    ),

    a: ({ children, href }: { children?: React.ReactNode; href?: string }) => (
        <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-nvidia hover:text-nvidia/80 underline underline-offset-2 transition-colors"
        >
            {children}
        </a>
    ),

    code: ({ className, children }: { className?: string; children?: React.ReactNode }) => {
        const match = /language-(\w+)/.exec(className || '');
        const isInline = !className;

        if (isInline) {
            return (
                <code className="px-1.5 py-0.5 rounded bg-dark-800 text-nvidia text-[13px] font-mono border border-dark-600">
                    {children}
                </code>
            );
        }

        return (
            <CodeBlock
                language={match ? match[1] : ''}
                value={String(children).replace(/\n$/, '')}
            />
        );
    },

    pre: ({ children }: { children?: React.ReactNode }) => (
        <div className="contents">
            {children}
        </div>
    ),

};
