import type {
  Citation,
  DynamicSource,
  Language,
  LiveSource,
  QueryDiagnostics,
  QueryResult,
  ThreadSummary,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    jsonFetch<{ status: string; vector_store_ready: boolean; supabase_configured: boolean }>(
      "/api/health"
    ),
  domains: () => jsonFetch<{ domains: string[] }>("/api/domains"),
  sources: () => jsonFetch<{ dynamic_sources: DynamicSource[] }>("/api/sources"),
  listChats: () => jsonFetch<{ chats: ThreadSummary[] }>("/api/chats"),
  newChat: () => jsonFetch<{ conversation_id: string; messages: [] }>("/api/chat/new", { method: "POST" }),
  getChat: (id: string) => jsonFetch<{ conversation_id: string; messages: any[] }>(`/api/chat/${id}`),
  deleteChat: (id: string) => jsonFetch(`/api/chat/${id}`, { method: "DELETE" }),
  renameChat: (id: string, name: string) =>
    jsonFetch(`/api/chat/${id}/name`, { method: "PUT", body: JSON.stringify({ name }) }),
  query: (question: string, language: Language, conversation_id?: string) =>
    jsonFetch<QueryResult>("/api/query", {
      method: "POST",
      body: JSON.stringify({ question, language, conversation_id }),
    }),
  uploadPdf: async (domain: string, file: File) => {
    const form = new FormData();
    form.append("domain", domain);
    form.append("pdf", file);
    const res = await fetch(`${BASE}/api/upload-pdf`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
};

export interface StreamHandlers {
  onMeta?: (m: {
    conversation_id: string;
    domain: string;
    language: Language;
    diagnostics?: QueryDiagnostics;
    _rewritten?: boolean;
    _cached?: boolean;
  }) => void;
  onToken?: (t: string) => void;
  onReplace?: (full: string) => void;
  onDone?: (d: {
    answer: string;
    citations: Citation[];
    live_sources: LiveSource[];
    context_notice: string;
    context_sources: string[];
    diagnostics?: QueryDiagnostics;
  }) => void;
  onError?: (msg: string) => void;
}

/** Consume the /api/query/stream SSE endpoint via fetch + ReadableStream. */
export async function streamQuery(
  question: string,
  language: Language,
  conversationId: string | undefined,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, language, conversation_id: conversationId }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const lines = frame.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "meta") handlers.onMeta?.(payload);
      else if (event === "token") handlers.onToken?.(payload.value);
      else if (event === "replace") handlers.onReplace?.(payload.value);
      else if (event === "done") handlers.onDone?.(payload);
      else if (event === "error") handlers.onError?.(payload.message);
    }
  }
}
