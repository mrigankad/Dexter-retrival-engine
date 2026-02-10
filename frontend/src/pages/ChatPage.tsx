import { ChatInterface } from '@/components/ChatInterface';

export function ChatPage() {
    return (
        <div className="h-full flex flex-col bg-dark-950">
            <div className="flex-1 overflow-hidden">
                <ChatInterface />
            </div>
        </div>
    );
}
