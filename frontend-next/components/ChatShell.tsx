"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { api, streamQuery } from "@/lib/api";
import { makeThreadTitle } from "@/lib/chatActions.mjs";
import { useChat } from "@/lib/store";
import type { DynamicSource } from "@/lib/types";
import Sidebar from "./Sidebar";
import ChatColumn from "./ChatColumn";
import InsightsPanel from "./InsightsPanel";

export default function ChatShell() {
  const {
    activeId,
    language,
    setActive,
    setMessages,
    setThreads,
    addMessage,
    appendToLast,
    replaceLast,
    updateLastMeta,
    setStreaming,
    setInsights,
    upsertThread,
  } = useChat();

  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [sources, setSources] = useState<DynamicSource[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(false);
  const streamRunRef = useRef(0);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status === "ok" ? "ok" : "down"))
      .catch(() => setHealth("down"));
    api.sources().then((s) => setSources(s.dynamic_sources)).catch(() => {});
    api.listChats().then((d) => setThreads(d.chats)).catch(() => {});
  }, [setThreads]);

  const startNewChat = useCallback(() => {
    streamRunRef.current += 1;
    setStreaming(false);
    setActive(null);
    setMessages([]);
    setInsights({ citations: [], liveSources: [], contextNotice: "", domain: "-" });
  }, [setActive, setMessages, setInsights, setStreaming]);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q) return;
      const isNewConversation = !activeId;
      addMessage({ role: "user", content: q });
      addMessage({ role: "assistant", content: "" });
      setStreaming(true);

      const runId = ++streamRunRef.current;
      const isCurrentRun = () => streamRunRef.current === runId;
      let convId = activeId ?? undefined;
      try {
        await streamQuery(q, language, convId, {
          onMeta: (m) => {
            if (!isCurrentRun()) return;
            convId = m.conversation_id;
            setActive(m.conversation_id);
            setInsights({ domain: m.domain });
            updateLastMeta({ domain: m.domain, language: m.language, diagnostics: m.diagnostics });
            if (isNewConversation) {
              upsertThread({ id: m.conversation_id, title: makeThreadTitle(q) });
            }
          },
          onToken: (t) => {
            if (isCurrentRun()) appendToLast(t);
          },
          onReplace: (full) => {
            if (isCurrentRun()) replaceLast(full);
          },
          onDone: (d) => {
            if (!isCurrentRun()) return;
            if (d.answer) replaceLast(d.answer);
            setInsights({
              citations: d.citations ?? [],
              liveSources: d.live_sources ?? [],
              contextNotice: d.context_notice ?? "",
            });
            updateLastMeta({
              citations: d.citations ?? [],
              live_sources: d.live_sources ?? [],
              context_notice: d.context_notice ?? "",
              diagnostics: d.diagnostics,
            });
          },
          onError: (msg) => {
            if (isCurrentRun()) replaceLast(`Request failed: ${msg}`);
          },
        });
      } catch (e: any) {
        if (isCurrentRun()) replaceLast(`Request failed: ${e?.message ?? e}`);
      } finally {
        if (isCurrentRun()) setStreaming(false);
      }
    },
    [
      activeId,
      language,
      addMessage,
      appendToLast,
      replaceLast,
      updateLastMeta,
      setActive,
      setInsights,
      setStreaming,
      upsertThread,
    ]
  );

  const openThread = useCallback(
    async (id: string) => {
      streamRunRef.current += 1;
      setStreaming(false);
      setActive(id);
      try {
        const data = await api.getChat(id);
        setMessages(
          (data.messages || []).map((m: any) => ({
            role: m.role,
            content: m.content,
            meta: m.meta,
          }))
        );
        const lastAssistant = [...(data.messages || [])].reverse().find((m: any) => m.role === "assistant");
        if (lastAssistant?.meta) {
          setInsights({
            citations: lastAssistant.meta.citations ?? [],
            liveSources: lastAssistant.meta.live_sources ?? [],
            contextNotice: lastAssistant.meta.context_notice ?? "",
            domain: lastAssistant.meta.domain ?? "-",
          });
        }
      } catch {
        /* ignore */
      }
      setSidebarOpen(false);
    },
    [setActive, setMessages, setInsights, setStreaming]
  );

  return (
    <main className="mx-auto flex h-[100dvh] max-w-[1680px] gap-2 overflow-hidden p-2 sm:gap-3 lg:p-4">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={startNewChat}
        onOpenThread={openThread}
      />
      <ChatColumn
        health={health}
        onSend={send}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        onToggleInsights={() => setInsightsOpen((v) => !v)}
        insightsOpen={insightsOpen}
      />
      <AnimatePresence>
        {insightsOpen && <InsightsPanel sources={sources} onClose={() => setInsightsOpen(false)} />}
      </AnimatePresence>
    </main>
  );
}
