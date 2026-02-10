/**
 * StreamingCursor — Visual indicator that text is still arriving.
 *
 * A blinking cursor block that shows during active token streaming.
 * Disappears with a smooth fade when streaming completes.
 */

import { motion } from 'framer-motion';

interface StreamingCursorProps {
    isVisible: boolean;
}

export function StreamingCursor({ isVisible }: StreamingCursorProps) {
    if (!isVisible) return null;

    return (
        <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="inline-block ml-0.5 relative"
        >
            <span className="streaming-cursor">▍</span>
        </motion.span>
    );
}

/**
 * ThinkingIndicator — Shows when waiting for first token.
 * 
 * Animated dots with a shimmer effect.
 */
export function ThinkingIndicator() {
    return (
        <div className="flex items-center gap-3 py-3">
            <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-nvidia thinking-dot" />
                <span className="w-2 h-2 rounded-full bg-nvidia thinking-dot" />
                <span className="w-2 h-2 rounded-full bg-nvidia thinking-dot" />
            </div>
            <span className="text-sm text-dark-400 animate-pulse">Reasoning...</span>
        </div>
    );
}
