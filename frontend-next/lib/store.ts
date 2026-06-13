import { create } from "zustand";
import type { Citation, Language, LiveSource, ChatMessage, QueryDiagnostics, ThreadSummary } from "./types";

interface ChatState {
  threads: ThreadSummary[];
  activeId: string | null;
  messages: ChatMessage[];
  language: Language;
  streaming: boolean;
  contextNotice: string;
  citations: Citation[];
  liveSources: LiveSource[];
  domain: string;

  setLanguage: (l: Language) => void;
  setThreads: (t: ThreadSummary[]) => void;
  setActive: (id: string | null) => void;
  setMessages: (m: ChatMessage[]) => void;
  addMessage: (m: ChatMessage) => void;
  appendToLast: (delta: string) => void;
  replaceLast: (full: string) => void;
  updateLastMeta: (meta: ChatMessage["meta"]) => void;
  setStreaming: (s: boolean) => void;
  setInsights: (p: {
    contextNotice?: string;
    citations?: Citation[];
    liveSources?: LiveSource[];
    domain?: string;
    diagnostics?: QueryDiagnostics;
  }) => void;
  upsertThread: (t: ThreadSummary) => void;
  removeThread: (id: string) => void;
}

export const useChat = create<ChatState>((set) => ({
  threads: [],
  activeId: null,
  messages: [],
  language: "en",
  streaming: false,
  contextNotice: "",
  citations: [],
  liveSources: [],
  domain: "-",

  setLanguage: (language) => set({ language }),
  setThreads: (threads) => set({ threads }),
  setActive: (activeId) => set({ activeId }),
  setMessages: (messages) => set({ messages }),
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  appendToLast: (delta) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") last.content += delta;
      return { messages };
    }),
  replaceLast: (full) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") last.content = full;
      return { messages };
    }),
  updateLastMeta: (meta) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        last.meta = { ...(last.meta || {}), ...(meta || {}) };
      }
      return { messages };
    }),
  setStreaming: (streaming) => set({ streaming }),
  setInsights: (p) =>
    set((s) => ({
      contextNotice: p.contextNotice ?? s.contextNotice,
      citations: p.citations ?? s.citations,
      liveSources: p.liveSources ?? s.liveSources,
      domain: p.domain ?? s.domain,
    })),
  upsertThread: (t) =>
    set((s) => {
      const exists = s.threads.find((x) => x.id === t.id);
      return { threads: exists ? s.threads.map((x) => (x.id === t.id ? t : x)) : [t, ...s.threads] };
    }),
  removeThread: (id) => set((s) => ({ threads: s.threads.filter((x) => x.id !== id) })),
}));
