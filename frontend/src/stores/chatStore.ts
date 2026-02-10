/**
 * Chat Store — Production State Machine.
 *
 * Manages:
 * - Message list with status tracking
 * - Streaming state per-message
 * - Source accumulation during streaming
 * - Error/retry state
 * - Conversation persistence (localStorage)
 * - Active AbortController reference
 */

import { create } from 'zustand';
import type { Message, Source, MessageStatus } from '@/types';
import { streamChat } from '@/api/chatStream';

// ── Helpers ──────────────────────────────────────────────────

let _msgCounter = 0;
function generateMessageId(): string {
    _msgCounter++;
    return `msg_${Date.now()}_${_msgCounter}_${Math.random().toString(36).substring(2, 7)}`;
}

const STORAGE_KEY = 'rag-chat-history';
const MAX_STORED_MESSAGES = 200;

function loadMessages(): Message[] {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw) as Message[];
        return parsed.map((m) => ({
            ...m,
            timestamp: new Date(m.timestamp),
            // Reset any streaming messages from previous sessions
            status: m.status === 'streaming' || m.status === 'thinking' ? 'error' as MessageStatus : m.status,
        }));
    } catch {
        return [];
    }
}

function persistMessages(messages: Message[]): void {
    try {
        const toStore = messages.slice(-MAX_STORED_MESSAGES);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
    } catch {
        // localStorage full or blocked — ignore
    }
}

// ── Store Interface ─────────────────────────────────────────

interface ChatState {
    messages: Message[];
    sessionId: string | null;
    isStreaming: boolean;
    isLoading: boolean;
    useRag: boolean;
    selectedDocumentIds: string[];
    streamingMessageId: string | null;
    activeAbortController: AbortController | null;

    // === Actions ===
    // Message lifecycle
    addUserMessage: (text: string) => void;
    startAssistantMessage: () => string;
    appendToken: (id: string, token: string) => void;
    addSources: (id: string, sources: Source[]) => void;
    finalizeMessage: (id: string) => void;
    failMessage: (id: string, error?: string) => void;
    setMessageStatus: (id: string, status: MessageStatus) => void;

    // Streaming control
    sendMessage: (content: string) => void;
    cancelStream: () => void;
    retryMessage: (messageId: string) => void;

    // Settings
    setUseRag: (useRag: boolean) => void;
    setSessionId: (sessionId: string) => void;
    setSelectedDocumentIds: (ids: string[]) => void;
    toggleDocumentSelection: (id: string) => void;

    // Conversation management
    clearMessages: () => void;
    addMetadata: (id: string, metadata: Record<string, any>) => void;
}

// ── Store Implementation ────────────────────────────────────

export const useChatStore = create<ChatState>((set, get) => ({
    messages: loadMessages(),
    sessionId: null,
    isStreaming: false,
    isLoading: false,
    useRag: true,
    selectedDocumentIds: [],
    streamingMessageId: null,
    activeAbortController: null,

    // ── Message Lifecycle ──────────────────────────────────
    // ... (rest of the store)

    // ── Message Lifecycle ──────────────────────────────────

    addUserMessage: (text: string) => {
        const message: Message = {
            id: generateMessageId(),
            role: 'user',
            content: text.trim(),
            timestamp: new Date(),
            status: 'done',
        };
        set((state) => {
            const messages = [...state.messages, message];
            persistMessages(messages);
            return { messages };
        });
    },

    startAssistantMessage: () => {
        const id = generateMessageId();
        const message: Message = {
            id,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            status: 'thinking',
            sources: [],
        };
        set((state) => ({
            messages: [...state.messages, message],
            streamingMessageId: id,
            isStreaming: true,
        }));
        return id;
    },

    appendToken: (id: string, token: string) => {
        set((state) => ({
            messages: state.messages.map((msg) =>
                msg.id === id
                    ? { ...msg, content: msg.content + token, status: 'streaming' as MessageStatus }
                    : msg
            ),
        }));
    },

    addSources: (id: string, sources: Source[]) => {
        set((state) => ({
            messages: state.messages.map((msg) =>
                msg.id === id
                    ? {
                        ...msg,
                        sources: [
                            ...(msg.sources || []),
                            ...sources.filter(
                                (s) => !(msg.sources || []).some(
                                    (existing) => existing.source === s.source && existing.page === s.page && existing.chunk_index === s.chunk_index
                                )
                            ),
                        ],
                    }
                    : msg
            ),
        }));
    },

    finalizeMessage: (id: string) => {
        set((state) => {
            const messages = state.messages.map((msg) =>
                msg.id === id ? { ...msg, status: 'done' as MessageStatus } : msg
            );
            persistMessages(messages);
            return {
                messages,
                isStreaming: false,
                streamingMessageId: null,
                activeAbortController: null,
            };
        });
    },

    failMessage: (id: string, error?: string) => {
        set((state) => {
            const messages = state.messages.map((msg) =>
                msg.id === id
                    ? {
                        ...msg,
                        status: 'error' as MessageStatus,
                        error: error || 'An error occurred',
                        // Preserve partial content — don't wipe
                    }
                    : msg
            );
            persistMessages(messages);
            return {
                messages,
                isStreaming: false,
                streamingMessageId: null,
                activeAbortController: null,
            };
        });
    },

    setMessageStatus: (id: string, status: MessageStatus) => {
        set((state) => ({
            messages: state.messages.map((msg) =>
                msg.id === id ? { ...msg, status } : msg
            ),
        }));
    },

    // ── Streaming Control ─────────────────────────────────

    sendMessage: (content: string) => {
        const state = get();

        // Auto-cancel any active stream
        if (state.isStreaming && state.activeAbortController) {
            state.activeAbortController.abort();
            if (state.streamingMessageId) {
                // Finalize the interrupted message with whatever content it has
                set((s) => ({
                    messages: s.messages.map((msg) =>
                        msg.id === s.streamingMessageId
                            ? { ...msg, status: 'done' as MessageStatus }
                            : msg
                    ),
                }));
            }
        }

        // Add user message
        get().addUserMessage(content);

        // Start assistant placeholder
        const assistantId = get().startAssistantMessage();

        // Start streaming
        const controller = streamChat(
            {
                query: content.trim(),
                stream: true,
                use_rag: get().useRag,
                session_id: get().sessionId || undefined,
                document_ids: get().selectedDocumentIds.filter(Boolean).length > 0 ? get().selectedDocumentIds.filter(Boolean) : undefined,
            },
            {
                onToken: (token) => {
                    get().appendToken(assistantId, token);
                },
                onSources: (sources) => {
                    get().addSources(assistantId, sources);
                },
                onDone: () => {
                    get().finalizeMessage(assistantId);
                },
                onError: (error) => {
                    get().failMessage(assistantId, error);
                },
                onStart: (sessionId) => {
                    if (sessionId && !sessionId.startsWith('session_')) {
                        set({ sessionId });
                    }
                },
                onMetadata: (data: any) => {
                    if (data.message_id) {
                        get().addMetadata(assistantId, { backend_id: data.message_id });
                    }
                    if (data.evaluation) {
                        get().addMetadata(assistantId, { evaluation: data.evaluation });
                    }
                },
            }
        );

        set({ activeAbortController: controller });
    },

    addMetadata: (id: string, metadata: Record<string, any>) => {
        set((state) => ({
            messages: state.messages.map((msg) =>
                msg.id === id
                    ? {
                        ...msg,
                        backend_id: metadata.backend_id || msg.backend_id,
                        evaluation: metadata.evaluation || msg.evaluation,
                    }
                    : msg
            ),
        }));
    },

    cancelStream: () => {
        const state = get();
        if (state.activeAbortController) {
            state.activeAbortController.abort();
        }
        if (state.streamingMessageId) {
            // Mark as done with partial content — don't wipe
            get().finalizeMessage(state.streamingMessageId);
        }
        set({
            isStreaming: false,
            streamingMessageId: null,
            activeAbortController: null,
        });
    },

    retryMessage: (messageId: string) => {
        const state = get();
        // Find the user message that preceded this assistant message
        const msgIndex = state.messages.findIndex((m) => m.id === messageId);
        if (msgIndex < 1) return;

        // Get the user query that led to this message
        const userMessage = state.messages
            .slice(0, msgIndex)
            .reverse()
            .find((m) => m.role === 'user');
        if (!userMessage) return;

        // Remove the failed assistant message
        set((s) => ({
            messages: s.messages.filter((m) => m.id !== messageId),
        }));

        // Re-send the query — this will create a new assistant message
        const assistantId = get().startAssistantMessage();

        const controller = streamChat(
            {
                query: userMessage.content,
                stream: true,
                use_rag: get().useRag,
                session_id: get().sessionId || undefined,
                document_ids: get().selectedDocumentIds.filter(Boolean).length > 0 ? get().selectedDocumentIds.filter(Boolean) : undefined,
            },
            {
                onToken: (token) => {
                    get().appendToken(assistantId, token);
                },
                onSources: (sources) => {
                    get().addSources(assistantId, sources);
                },
                onDone: () => {
                    get().finalizeMessage(assistantId);
                },
                onError: (error) => {
                    get().failMessage(assistantId, error);
                },
            }
        );

        set({ activeAbortController: controller });
    },

    // ── Settings ──────────────────────────────────────────

    setUseRag: (useRag: boolean) => set({ useRag }),

    setSessionId: (sessionId: string) => set({ sessionId }),

    setSelectedDocumentIds: (ids: string[]) => set({ selectedDocumentIds: ids }),

    toggleDocumentSelection: (id: string) => {
        if (!id) return;
        set((state) => {
            const isSelected = state.selectedDocumentIds.includes(id);
            const nextIds = isSelected
                ? state.selectedDocumentIds.filter((docId) => docId !== id)
                : [...state.selectedDocumentIds, id];
            return { selectedDocumentIds: nextIds };
        });
    },

    clearMessages: () => {
        const state = get();
        if (state.activeAbortController) {
            state.activeAbortController.abort();
        }
        localStorage.removeItem(STORAGE_KEY);
        set({
            messages: [],
            sessionId: null,
            isStreaming: false,
            streamingMessageId: null,
            activeAbortController: null,
        });
    },
}));
