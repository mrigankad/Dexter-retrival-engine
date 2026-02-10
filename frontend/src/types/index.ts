// =====================
// Stream Event Types (Event-Driven Architecture)
// =====================
export type StreamEventType = 'token' | 'sources' | 'done' | 'error' | 'start' | 'metadata';

export interface StreamEvent {
    type: StreamEventType;
    data: unknown;
}

export interface TokenEvent extends StreamEvent {
    type: 'token';
    data: string;
}

export interface SourcesEvent extends StreamEvent {
    type: 'sources';
    data: Source[];
}

export interface DoneEvent extends StreamEvent {
    type: 'done';
    data: string;
}

export interface ErrorEvent extends StreamEvent {
    type: 'error';
    data: string;
}

export interface MetadataEvent extends StreamEvent {
    type: 'metadata';
    data: {
        session_id?: string;
        route?: string;
        usage?: Record<string, unknown>;
    };
}

// =====================
// Message Status State Machine
// =====================
export type MessageStatus = 'streaming' | 'done' | 'error' | 'thinking';

// =====================
// Chat Types
// =====================
export interface Source {
    source: string;
    page: number | string;
    total_pages: number | string;
    chunk_index: number;
    score: number;
    rerank_score?: number | null;
    content_type?: string;
    asset_path?: string;
    asset_id?: string;
    document_id?: string;
    snippet?: string;
    bbox?: number[];
}

export interface Message {
    id: string;
    backend_id?: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: Date;
    sources?: Source[];
    status: MessageStatus;
    evaluation?: EvaluationScores;
    error?: string;
}

export interface Conversation {
    id: string;
    title: string;
    messages: Message[];
    createdAt: Date;
    updatedAt: Date;
    sessionId?: string;
}

export interface EvaluationScores {
    faithfulness?: number;
    relevance?: number;
    precision?: number;
    recall?: number;
}

export interface ChatRequest {
    query: string;
    session_id?: string;
    stream?: boolean;
    use_rag?: boolean;
    document_ids?: string[];
}

export interface ChatResponse {
    response: string;
    session_id: string;
    sources: Source[];
    usage: Record<string, unknown>;
    route: string;
}

// =====================
// Stream Handlers Interface
// =====================
export interface StreamHandlers {
    onToken: (token: string) => void;
    onSources: (sources: Source[]) => void;
    onDone: () => void;
    onError: (error: string) => void;
    onStart?: (sessionId: string) => void;
    onMetadata?: (data: MetadataEvent['data']) => void;
}

// =====================
// Document Types
// =====================
export interface Document {
    id: string;
    filename: string;
    status: 'processing' | 'completed' | 'failed';
    uploaded_at: string;
    chunks_count?: number;
    total_pages?: number;
    file_size?: number;
}

export interface UploadResponse {
    document_id: string;
    filename: string;
    status: string;
    message: string;
}

// =====================
// Auth Types
// =====================
export interface User {
    id: string;
    username: string;
    email: string;
}

export interface AuthTokens {
    access_token: string;
    refresh_token?: string;
    token_type: string;
    expires_in: number;
}

export interface LoginRequest {
    username: string;
    password: string;
}

// =====================
// Health Types
// =====================
export interface HealthStatus {
    status: string;
    timestamp: string;
    version: string;
    environment: string;
    services: {
        redis: ServiceHealth;
        qdrant: ServiceHealth;
    };
}

export interface ServiceHealth {
    status: string;
    latency_ms: number;
    error: string | null;
}
