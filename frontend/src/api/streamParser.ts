/**
 * SSE Stream Parser — Production-grade event parsing.
 *
 * Handles:
 * - Partial chunks split across ReadableStream reads
 * - Multi-line SSE events
 * - JSON parsing with fallback
 * - Event type discrimination
 */

export interface ParsedSSEEvent {
    event: string;
    data: string;
}

/**
 * Parse SSE lines from a raw text buffer.
 * Returns parsed events and any remaining incomplete buffer.
 */
export function parseSSEBuffer(
    buffer: string
): { events: ParsedSSEEvent[]; remaining: string } {
    const events: ParsedSSEEvent[] = [];
    const lines = buffer.split('\n');

    // The last element may be an incomplete line — keep it as remaining
    const remaining = lines.pop() || '';

    let currentEvent = 'message';
    let currentData = '';

    for (const line of lines) {
        if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
            // Preserve whitespace in data — critical for token streaming
            currentData = line.slice(6);
        } else if (line === '' && currentData !== '') {
            // Empty line = end of SSE event
            events.push({ event: currentEvent, data: currentData });
            currentEvent = 'message';
            currentData = '';
        } else if (line === '' && currentEvent !== 'message') {
            // Event with empty data
            // Reset
            currentEvent = 'message';
        }
    }

    // If we have data but no terminating empty line yet, put it back in the remaining buffer
    let remainingBuffer = remaining;
    if (currentData !== '' || currentEvent !== 'message') {
        // Reconstruct the incomplete event
        if (currentEvent !== 'message') {
            remainingBuffer = `event: ${currentEvent}\n` + remainingBuffer;
        }
        if (currentData !== '') {
            remainingBuffer = `data: ${currentData}\n` + remainingBuffer;
        }
    }

    return { events, remaining: remainingBuffer };
}

/**
 * Safely parse JSON data from an SSE event.
 * Returns the parsed object or null if parsing fails.
 */
export function safeParseJSON<T = unknown>(data: string): T | null {
    try {
        return JSON.parse(data) as T;
    } catch {
        return null;
    }
}
