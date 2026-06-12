"use client";

import { useCallback, useEffect, useState } from "react";
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
    setStreaming,
    setInsights,
    upsertThread,
  } = useChat();

  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [domains, setDomains] = useState<string[]>([]);
  const [sources, setSources] = useState<DynamicSource[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status === "ok" ? "ok" : "down"))
      .catch(() => setHealth("down"));
    api.domains().then((d) => setDomains(d.domains)).catch(() => {});
    api.sources().then((s) => setSources(s.dynamic_sources)).catch(() => {});
    api.listChats().then((d) => setThreads(d.chats)).catch(() => {});
  }, [setThreads]);

  const startNewChat = useCallback(() => {
    setActive(null);
    setMessages([]);
    setInsights({ citations: [], liveSources: [], contextNotice: "", domain: "-" });
  }, [setActive, setMessages, setInsights]);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q) return;
      const isNewConversation = !activeId;
      addMessage({ role: "user", content: q });
      addMessage({ role: "assistant", content: "" });
      setStreaming(true);

      let convId = activeId ?? undefined;
      try {
        await streamQuery(q, language, convId, {
          onMeta: (m) => {
            convId = m.conversation_id;
            setActive(m.conversation_id);
            setInsights({ domain: m.domain });
            if (isNewConversation) {
              upsertThread({ id: m.conversation_id, title: makeThreadTitle(q) });
            }
          },
          onToken: (t) => appendToLast(t),
          onReplace: (full) => replaceLast(full),
          onDone: (d) => {
            if (d.answer) replaceLast(d.answer);
            setInsights({
              citations: d.citations ?? [],
              liveSources: d.live_sources ?? [],
              contextNotice: d.context_notice ?? "",
            });
          },
          onError: (msg) => replaceLast(`Request failed: ${msg}`),
        });
      } catch (e: any) {
        replaceLast(`Request failed: ${e?.message ?? e}`);
      } finally {
        setStreaming(false);
      }
    },
    [
      activeId,
      language,
      addMessage,
      appendToLast,
      replaceLast,
      setActive,
      setInsights,
      setStreaming,
      upsertThread,
    ]
  );

  const openThread = useCallback(
    async (id: string) => {
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
    [setActive, setMessages, setInsights]
  );

  return (
    <main className="mx-auto flex h-screen max-w-[1600px] gap-3 p-3">
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
      {insightsOpen && (
        <InsightsPanel domains={domains} sources={sources} onClose={() => setInsightsOpen(false)} />
      )}
    </main>
  );
}
