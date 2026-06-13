export type Language = "en" | "hi";

export interface Citation {
  id: number;
  section: string;
  source: string;
  domain: string;
  score: number | null;
}

export interface LiveSource {
  label: string;
  url: string;
  snippet: string;
}

export interface QueryDiagnostics {
  query_type?: string;
  needs_retrieval?: boolean;
  rewritten?: boolean;
  reason?: string;
  issues?: string[];
  domain_hint?: string;
  retrieval_count?: number;
  grounded_issue_count?: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  meta?: {
    language?: Language;
    domain?: string;
    citations?: Citation[];
    live_sources?: LiveSource[];
    context_notice?: string;
    diagnostics?: QueryDiagnostics;
  };
}

export interface QueryResult {
  conversation_id: string;
  question: string;
  effective_question?: string;
  domain: string;
  language: Language;
  domain_scores?: Record<string, number>;
  answer: string;
  context_sources: string[];
  context_source_label: string;
  context_notice: string;
  citations: Citation[];
  live_sources: LiveSource[];
  diagnostics?: QueryDiagnostics;
  _cached?: boolean;
  _rewritten?: boolean;
}

export interface DynamicSource {
  url: string;
  label: string;
  domain: string;
  enabled?: boolean;
  refresh_days?: number;
}

export interface ThreadSummary {
  id: string;
  title: string;
  updated_at?: string;
  created_at?: string;
  message_count?: number;
  domain?: string;
  language?: Language;
}
