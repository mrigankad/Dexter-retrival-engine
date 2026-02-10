/**
 * ChatInput — Production chat input with streaming controls.
 *
 * Features:
 * - Auto-resize textarea
 * - Enter/Shift+Enter keyboard shortcuts
 * - Stop generation button during streaming
 * - RAG/Direct mode toggle
 * - Character counter
 * - Sticky bottom position
 */

import { useState, useRef, useCallback, KeyboardEvent } from 'react';
import { useChatStore } from '@/stores/chatStore';
import {
    PaperAirplaneIcon,
    StopIcon,
    AdjustmentsHorizontalIcon,
    SparklesIcon,
    BoltIcon,
    TrashIcon,
} from '@heroicons/react/24/solid';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

const MAX_CHARS = 10000;

export function ChatInput() {
    const [input, setInput] = useState('');
    const [showSettings, setShowSettings] = useState(false);
    const {
        isStreaming,
        useRag,
        setUseRag,
        sendMessage,
        cancelStream,
        clearMessages,
    } = useChatStore();
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const isDisabled = isStreaming;
    const canSend = input.trim().length > 0 && !isDisabled;

    const handleSubmit = useCallback(() => {
        if (!canSend) return;
        sendMessage(input);
        setInput('');
        // Reset textarea height
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
        }
    }, [canSend, input, sendMessage]);

    const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    }, [handleSubmit]);

    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const value = e.target.value;
        if (value.length > MAX_CHARS) return;
        setInput(value);
        // Auto-resize textarea
        const textarea = e.target;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    };

    const charCount = input.length;
    const nearLimit = charCount > MAX_CHARS * 0.9;

    return (
        <div className="max-w-4xl mx-auto space-y-3">
            {/* Settings Panel */}
            <AnimatePresence>
                {showSettings && (
                    <motion.div
                        initial={{ opacity: 0, height: 0, y: 8 }}
                        animate={{ opacity: 1, height: 'auto', y: 0 }}
                        exit={{ opacity: 0, height: 0, y: 8 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="flex items-center gap-4 px-4 py-3 rounded-xl glass">
                            {/* RAG Toggle */}
                            <div className="flex items-center gap-3">
                                <span className="text-sm text-dark-400">Mode:</span>
                                <button
                                    onClick={() => setUseRag(true)}
                                    className={clsx(
                                        "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all",
                                        useRag
                                            ? "bg-nvidia text-white shadow-sm shadow-nvidia/20"
                                            : "bg-dark-800 text-dark-400 hover:text-white"
                                    )}
                                >
                                    <SparklesIcon className="w-4 h-4" />
                                    RAG
                                </button>
                                <button
                                    onClick={() => setUseRag(false)}
                                    className={clsx(
                                        "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all",
                                        !useRag
                                            ? "bg-blue-500 text-white shadow-sm shadow-blue-500/20"
                                            : "bg-dark-800 text-dark-400 hover:text-white"
                                    )}
                                >
                                    <BoltIcon className="w-4 h-4" />
                                    Direct
                                </button>
                            </div>

                            <div className="flex-1" />

                            {/* Clear Chat */}
                            <button
                                onClick={clearMessages}
                                className="flex items-center gap-1.5 text-sm text-dark-400 hover:text-red-400 transition-colors"
                            >
                                <TrashIcon className="w-3.5 h-3.5" />
                                Clear Chat
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Input Container */}
            <div className="relative">
                <div className={clsx(
                    "flex items-end gap-3 p-3 rounded-2xl glass border transition-all duration-200",
                    isStreaming
                        ? "border-nvidia/30 shadow-sm shadow-nvidia/5"
                        : "border-dark-600 focus-within:border-nvidia/50 focus-within:shadow-sm focus-within:shadow-nvidia/5"
                )}>
                    {/* Settings Toggle */}
                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className={clsx(
                            "p-2 rounded-xl transition-all duration-200",
                            showSettings
                                ? "bg-nvidia text-white"
                                : "text-dark-400 hover:text-white hover:bg-dark-700"
                        )}
                        title="Settings"
                    >
                        <AdjustmentsHorizontalIcon className="w-5 h-5" />
                    </button>

                    {/* Text Input */}
                    <textarea
                        ref={textareaRef}
                        value={input}
                        onChange={handleInputChange}
                        onKeyDown={handleKeyDown}
                        placeholder={
                            isStreaming
                                ? "Waiting for response..."
                                : useRag
                                    ? "Ask about your documents..."
                                    : "Ask anything..."
                        }
                        className="flex-1 bg-transparent text-white placeholder-dark-500 resize-none focus:outline-none min-h-[24px] max-h-[200px] py-1"
                        rows={1}
                        disabled={isStreaming}
                    />

                    {/* Character Counter */}
                    {charCount > 0 && (
                        <span className={clsx(
                            "text-[10px] font-mono pb-1 transition-colors",
                            nearLimit ? "text-red-400" : "text-dark-600"
                        )}>
                            {charCount}/{MAX_CHARS}
                        </span>
                    )}

                    {/* Send/Stop Button */}
                    {isStreaming ? (
                        <button
                            onClick={cancelStream}
                            className="p-3 rounded-xl bg-red-500 text-white hover:bg-red-600 transition-all duration-200 shadow-sm shadow-red-500/20 flex items-center gap-2"
                            title="Stop generating"
                        >
                            <StopIcon className="w-5 h-5" />
                            <span className="text-sm font-medium pr-1">Stop</span>
                        </button>
                    ) : (
                        <button
                            onClick={handleSubmit}
                            disabled={!canSend}
                            className={clsx(
                                "p-3 rounded-xl transition-all duration-200",
                                canSend
                                    ? "bg-nvidia text-white hover:bg-nvidia-dark shadow-sm shadow-nvidia/20"
                                    : "bg-dark-700 text-dark-500 cursor-not-allowed"
                            )}
                            title="Send message (Enter)"
                        >
                            <PaperAirplaneIcon className="w-5 h-5" />
                        </button>
                    )}
                </div>

                {/* Bottom Indicators */}
                <div className="flex items-center justify-between mt-2 px-1">
                    {/* Mode Indicator */}
                    <div className="flex items-center gap-2">
                        <div className={clsx(
                            "w-2 h-2 rounded-full transition-colors",
                            isStreaming
                                ? "bg-nvidia animate-pulse"
                                : useRag ? "bg-nvidia" : "bg-blue-500"
                        )} />
                        <span className="text-xs text-dark-500">
                            {isStreaming
                                ? "Generating response..."
                                : useRag
                                    ? "RAG Mode — Searching your documents"
                                    : "Direct Mode — Using LLM only"
                            }
                        </span>
                    </div>

                    {/* Keyboard Hint */}
                    <div className="hidden sm:flex items-center gap-1.5 text-[10px] text-dark-600">
                        <kbd className="px-1.5 py-0.5 rounded bg-dark-800 border border-dark-700 font-mono">Enter</kbd>
                        <span>to send</span>
                        <span className="text-dark-700">·</span>
                        <kbd className="px-1.5 py-0.5 rounded bg-dark-800 border border-dark-700 font-mono">Shift+Enter</kbd>
                        <span>new line</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
