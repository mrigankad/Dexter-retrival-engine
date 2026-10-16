// =====================
// Stream Event Types (Event-Driven Architecture)
// =====================
export type StreamEventType =
    | 'token' | 'answer_delta' | 'sources' | 'evidence' | 'progress' | 'warning'
    | 'table' | 'chart' | 'done' | 'error' | 'start' | 'metadata';

export type ProgressStage =
    | 'understanding' | 'routing' | 'planning' | 'retrieving' | 'reranking'
    | 'found_sources' | 'synthesizing' | 'verifying' | 'finalizing';

export interface ProgressEventData {
    stage: ProgressStage;
    label: string;
    detail?: Record<string, unknown>;
}

export interface EvidenceLocator {
    document_id?: string | null;
    page?: number | null;
    total_pages?: number | null;
    chunk_index?: number | null;
    section?: string | null;
    url?: string | null;
}

export interface Evidence {
    id: string;
    type: 'document' | 'sql' | 'web' | 'memory';
    source_name: string;
    title?: string | null;
    locator: EvidenceLocator;
    snippet: string;
    score: number;
    rerank_score?: number | null;
    backend: string;
    content_type: string;
}

export interface Citation {
    marker: string;
    evidence_id: string;
}

export interface TableBlockData {
    query_id: string;
    title?: string | null;
    columns: string[];
    rows: unknown[][];
    row_count: number;
    sql: string;
    connection: string;
}

export interface ChartBlockData {
    type: 'kpi' | 'line' | 'bar' | 'stacked_bar' | 'table';
    title: string;
    query_id?: string;
    x?: string;
    y?: string[];
    value?: unknown;
    label?: string;
    format?: Record<string, string>;
}

export type AnswerBlock =
    | { type: 'table'; data: TableBlockData }
    | { type: 'chart'; data: ChartBlockData }
    | { type: 'markdown' | 'kpi'; data: Record<string, unknown> };

export interface DoneEventData {
    answer_id: string;
    confidence: 'high' | 'medium' | 'low';
    latency_ms: number;
    trace_id?: string | null;
    session_id?: string | null;
    citations: Citation[];
    usage: Record<string, number>;
}

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
        message_id?: string;
        route?: string;
        trace_id?: string;
        intent?: string;
        confidence?: 'high' | 'medium' | 'low';
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
    evidence?: Evidence[];
    citations?: Citation[];
    blocks?: AnswerBlock[];
    status: MessageStatus;
    stage?: ProgressEventData;
    confidence?: 'high' | 'medium' | 'low';
    intent?: string;
    trace_id?: string;
    latency_ms?: number;
    warnings?: string[];
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
    onProgress?: (data: ProgressEventData) => void;
    onEvidence?: (evidence: Evidence[]) => void;
    onWarning?: (message: string) => void;
    onComplete?: (data: DoneEventData) => void;
    onBlock?: (block: AnswerBlock) => void;
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
    knowledge_backend?: string;
    llm_configured?: boolean;
    services: {
        redis: ServiceHealth;
        qdrant: ServiceHealth;
        database?: ServiceHealth;
        knowledge?: ServiceHealth;
    };
}

export interface ServiceHealth {
    status: string;
    latency_ms: number;
    error: string | null;
}
