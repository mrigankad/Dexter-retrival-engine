/**
 * Streaming Chat API Client — Fetch + ReadableStream.
 *
 * Uses the parsed SSE buffer for robust event handling.
 * Supports AbortController for cancellation.
 */

import { parseSSEBuffer, safeParseJSON } from './streamParser';
import { useAuthStore } from '@/stores/authStore';
import type { DoneEventData, Evidence, ProgressEventData, Source, StreamHandlers } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export interface StreamChatPayload {
    query: string;
    session_id?: string;
    stream: boolean;
    use_rag: boolean;
    document_ids?: string[];
}

/**
 * Stream a chat response using fetch + ReadableStream.
 *
 * Returns an AbortController that can be used to cancel the stream.
 * The handlers object receives typed events as they arrive.
 */
export function streamChat(
    payload: StreamChatPayload,
    handlers: StreamHandlers,
): AbortController {
    const controller = new AbortController();
    const token = useAuthStore.getState().token;

    const execute = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token && { Authorization: `Bearer ${token}` }),
                },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });

            if (!response.ok) {
                const errorText = await response.text().catch(() => 'Unknown error');
                handlers.onError(`HTTP ${response.status}: ${errorText}`);
                return;
            }

            const reader = response.body?.getReader();
            if (!reader) {
                handlers.onError('No response body received');
                return;
            }

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();

                if (done) {
                    // Process any remaining buffer
                    if (buffer.trim()) {
                        const { events } = parseSSEBuffer(buffer + '\n\n');
                        for (const event of events) {
                            dispatchEvent(event.event, event.data, handlers);
                        }
                    }
                    handlers.onDone();
                    break;
                }

                buffer += decoder.decode(value, { stream: true });

                // Parse complete SSE events from the buffer
                const { events, remaining } = parseSSEBuffer(buffer);
                buffer = remaining;

                for (const event of events) {
                    dispatchEvent(event.event, event.data, handlers);
                }
            }
        } catch (error: unknown) {
            if (error instanceof Error && error.name === 'AbortError') {
                // User cancelled — don't report as error
                return;
            }
            const message = error instanceof Error ? error.message : 'Stream connection failed';
            handlers.onError(message);
        }
    };

    execute();
    return controller;
}

/**
 * Dispatch a parsed SSE event to the appropriate handler.
 */
function dispatchEvent(
    eventType: string,
    data: string,
    handlers: StreamHandlers
): void {
    switch (eventType) {
        case 'token':
            handlers.onToken(data);
            break;

        case 'answer_delta': {
            const delta = safeParseJSON<{ text: string }>(data);
            if (delta && typeof delta.text === 'string') {
                handlers.onToken(delta.text);
            }
            break;
        }

        case 'progress': {
            const progress = safeParseJSON<ProgressEventData>(data);
            if (progress && progress.stage) {
                handlers.onProgress?.(progress);
            }
            break;
        }

        case 'evidence': {
            const evidence = safeParseJSON<Evidence[]>(data);
            if (evidence && Array.isArray(evidence)) {
                handlers.onEvidence?.(evidence);
            }
            break;
        }

        case 'warning': {
            const warning = safeParseJSON<{ message: string }>(data);
            if (warning?.message) {
                handlers.onWarning?.(warning.message);
            }
            break;
        }

        case 'sources': {
            const sources = safeParseJSON<Source[]>(data);
            if (sources && Array.isArray(sources)) {
                handlers.onSources(sources);
            }
            break;
        }

        case 'done': {
            // Stream end triggers handlers.onDone(); here we only surface the summary payload.
            const done = safeParseJSON<DoneEventData>(data);
            if (done && done.answer_id) {
                handlers.onComplete?.(done);
            }
            break;
        }

        case 'start':
            handlers.onStart?.(data);
            break;

        case 'error':
            handlers.onError(data);
            break;

        case 'metadata': {
            const meta = safeParseJSON(data);
            if (meta) {
                handlers.onMetadata?.(meta as Record<string, unknown>);
            }
            break;
        }

        default:
            // Unknown structured events are ignored rather than rendered as text.
            break;
    }
}
