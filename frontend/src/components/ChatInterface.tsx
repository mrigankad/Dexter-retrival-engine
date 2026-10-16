/**
 * ChatInterface — Production Chat Window.
 *
 * Features:
 * - Smart scroll: locks to bottom during streaming, releases on user scroll
 * - Empty state with example prompts
 * - Source panel integration
 * - Connected to the streaming chat store
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { SourcePanel } from './SourcePanel';
import { KnowledgeScopeSelector } from './KnowledgeScopeSelector';
import { SparklesIcon, ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';
import type { Source } from '@/types';

export function ChatInterface() {
    const { messages, isStreaming } = useChatStore();
    const [selectedSources, setSelectedSources] = useState<Source[]>([]);
    const [showSources, setShowSources] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [userScrolledUp, setUserScrolledUp] = useState(false);

    // ── Smart Scroll Control ────────────────────────────────
    // Lock to bottom during streaming unless user scrolls up

    const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
        messagesEndRef.current?.scrollIntoView({ behavior });
    }, []);

    // Detect when user scrolls up (disengages auto-scroll)
    const handleScroll = useCallback(() => {
        const container = scrollContainerRef.current;
        if (!container) return;

        const { scrollTop, scrollHeight, clientHeight } = container;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

        // If user scrolls more than 100px from bottom, release auto-scroll
        setUserScrolledUp(distanceFromBottom > 100);
    }, []);

    // Auto-scroll during streaming (unless user scrolled up)
    useEffect(() => {
        if (!userScrolledUp && (isStreaming || messages.length > 0)) {
            scrollToBottom();
        }
    }, [messages, isStreaming, userScrolledUp, scrollToBottom]);

    // When streaming starts, re-engage auto-scroll
    useEffect(() => {
        if (isStreaming) {
            setUserScrolledUp(false);
        }
    }, [isStreaming]);

    // ── Handlers ────────────────────────────────────────────
    const handleShowSources = useCallback((sources: Source[]) => {
        setSelectedSources(sources);
        setShowSources(true);
    }, []);

    const handleRetry = useCallback((messageId: string) => {
        useChatStore.getState().retryMessage(messageId);
    }, []);

    const handleExampleClick = useCallback((query: string) => {
        useChatStore.getState().sendMessage(query);
    }, []);

    return (
        <div className="flex h-full overflow-hidden">
            {/* Context/Knowledge Selector Sidebar */}
            <div className="hidden lg:block shrink-0">
                <KnowledgeScopeSelector />
            </div>

            {/* Chat Area */}
            <div className="flex-1 flex flex-col min-w-0 bg-dark-950">
                {/* Messages */}
                <div
                    ref={scrollContainerRef}
                    onScroll={handleScroll}
                    className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth custom-scrollbar"
                >
                    {messages.length === 0 ? (
                        <EmptyState onExampleClick={handleExampleClick} />
                    ) : (
                        <>
                            {messages.map((message) => (
                                <ChatMessage
                                    key={message.id}
                                    message={message}
                                    onShowSources={handleShowSources}
                                    onRetry={handleRetry}
                                />
                            ))}
                            <div ref={messagesEndRef} className="h-1" />
                        </>
                    )}
                </div>

                {/* Scroll to bottom button */}
                {userScrolledUp && messages.length > 0 && (
                    <div className="relative">
                        <button
                            onClick={() => {
                                setUserScrolledUp(false);
                                scrollToBottom();
                            }}
                            className="absolute bottom-20 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full glass border border-dark-600 text-dark-300 hover:text-white hover:border-nvidia/50 transition-all duration-200 shadow-lg text-sm flex items-center gap-2 z-10"
                        >
                            <ChatBubbleLeftRightIcon className="w-4 h-4" />
                            Scroll to bottom
                        </button>
                    </div>
                )}

                {/* Input */}
                <div className="p-4 border-t border-dark-700">
                    <ChatInput />
                </div>
            </div>

            {/* Sources Panel */}
            <SourcePanel
                sources={selectedSources}
                isOpen={showSources}
                onClose={() => setShowSources(false)}
            />
        </div>
    );
}

// ── Empty State ─────────────────────────────────────────────

function EmptyState({ onExampleClick }: { onExampleClick: (q: string) => void }) {
    const examples = [
        {
            icon: "📊",
            text: "What sustainability initiatives are mentioned?",
            category: "Analysis",
        },
        {
            icon: "📑",
            text: "Summarize the CSR projects with page numbers",
            category: "Summary",
        },
        {
            icon: "🌍",
            text: "What are the company's environmental policies?",
            category: "Research",
        },
        {
            icon: "💧",
            text: "Tell me about water consumption data",
            category: "Data",
        },
    ];

    return (
        <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-nvidia to-primary-500 flex items-center justify-center mb-6 animate-pulse-glow shadow-xl">
                <SparklesIcon className="w-10 h-10 text-white" />
            </div>

            <h2 className="text-2xl font-bold text-white mb-2">
                Welcome to <span className="gradient-text">Bodham</span>
            </h2>

            <p className="text-dark-400 max-w-md mb-8 leading-relaxed">
                Ask questions about your documents. I'll search through your knowledge base
                and provide answers with page citations and source references.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl w-full">
                {examples.map((example, i) => (
                    <button
                        key={i}
                        onClick={() => onExampleClick(example.text)}
                        className="p-4 text-left rounded-xl border border-dark-700 bg-dark-800/50 hover:bg-dark-800 hover:border-nvidia/40 transition-all duration-200 group"
                    >
                        <div className="flex items-center gap-2 mb-2">
                            <span className="text-lg">{example.icon}</span>
                            <span className="text-[10px] font-bold text-dark-500 uppercase tracking-wider group-hover:text-nvidia transition-colors">
                                {example.category}
                            </span>
                        </div>
                        <p className="text-sm text-dark-300 group-hover:text-white transition-colors leading-relaxed">
                            {example.text}
                        </p>
                    </button>
                ))}
            </div>

            <p className="text-xs text-dark-600 mt-8">
                Powered by NVIDIA NIM · Production RAG Engine
            </p>
        </div>
    );
}
