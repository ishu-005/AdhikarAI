"use client";

import { useEffect, useRef } from "react";
import {
  BadgeHelp,
  BriefcaseBusiness,
  FileSearch,
  Home,
  Menu,
  PanelRightOpen,
  ReceiptText,
  Scale,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { motion } from "framer-motion";
import { useChat } from "@/lib/store";
import MessageBubble from "./MessageBubble";
import Composer from "./Composer";

const STATUS: Record<string, { dot: string; label: string; text: string }> = {
  checking: { dot: "bg-amber-400", label: "connecting", text: "text-amber-500" },
  ok: { dot: "bg-emerald-400", label: "online", text: "text-emerald-500" },
  down: { dot: "bg-red-400", label: "offline", text: "text-red-500" },
};

const SUGGESTIONS = [
  { icon: ShieldCheck, q: "What are my rights if police arrest me?", label: "Arrest rights" },
  { icon: FileSearch, q: "How do I file an RTI application?", label: "RTI filing" },
  { icon: ReceiptText, q: "A shop refused to refund a defective product. What can I do?", label: "Refund issue" },
  { icon: BriefcaseBusiness, q: "My employer hasn't paid my salary. What are my options?", label: "Salary unpaid" },
  { icon: Scale, q: "What is the punishment for murder under the Bharatiya Nyaya Sanhita?", label: "BNS offence" },
  { icon: Home, q: "What documents must be registered under the Registration Act?", label: "Property docs" },
];

const FACTS = [
  "Knowledge questions get educational answers.",
  "Problem questions get grounded next steps.",
  "Citations show which legal chunks were used.",
];

export default function ChatColumn({
  health,
  onSend,
  onToggleSidebar,
  onToggleInsights,
  insightsOpen,
}: {
  health: "checking" | "ok" | "down";
  onSend: (q: string) => void;
  onToggleSidebar: () => void;
  onToggleInsights: () => void;
  insightsOpen: boolean;
}) {
  const { messages, streaming, contextNotice, domain, language, setLanguage } = useChat();
  const endRef = useRef<HTMLDivElement>(null);
  const st = STATUS[health];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <section className="glass relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl2 border border-line shadow-panel">
      <header className="flex min-h-[68px] items-center justify-between gap-2 border-b border-line px-3 py-2.5 sm:gap-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <button
            onClick={onToggleSidebar}
            className="grid h-9 w-9 place-items-center rounded-lg text-ink-muted transition hover:bg-raised hover:text-ink md:hidden"
            aria-label="Open conversations"
          >
            <Menu size={18} />
          </button>
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 font-display text-base font-semibold text-ink sm:text-lg">
              AdhikarAI Counsel
              <span className="hidden items-center gap-1 rounded-md bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand sm:inline-flex">
                <Sparkles size={10} /> cited answers
              </span>
            </h2>
            <p className="truncate text-xs text-ink-muted">
              {contextNotice || "Ask for legal knowledge or describe a real situation."}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <span className={`flex h-8 items-center gap-1.5 rounded-lg border border-line bg-raised px-2.5 text-[11px] font-semibold ${st.text}`}>
            <span className="relative flex h-2 w-2">
              {health === "ok" && <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald-400" />}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${st.dot}`} />
            </span>
            <span className="hidden sm:inline">{st.label}</span>
          </span>

          {domain && domain !== "-" && (
            <span className="hidden h-8 items-center rounded-lg border border-line bg-raised px-2.5 text-[11px] font-medium text-ink-muted md:inline-flex">
              {domain.replace(/_/g, " ")}
            </span>
          )}

          <div className="relative flex rounded-lg border border-line bg-raised p-0.5 text-[11px] font-semibold sm:text-xs">
            {(["en", "hi"] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLanguage(l)}
                className={`relative z-10 rounded-lg px-2.5 py-1 transition-colors ${
                  language === l ? "text-white" : "text-ink-muted hover:text-ink"
                }`}
              >
                {l === "en" ? "EN" : "HI"}
                {language === l && (
                  <motion.span
                    layoutId="lang-pill"
                    className="absolute inset-0 -z-10 rounded-md bg-brand-gradient"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
              </button>
            ))}
          </div>

          <button
            onClick={onToggleInsights}
            className={`grid h-9 w-9 place-items-center rounded-lg transition ${
              insightsOpen ? "bg-brand-soft text-brand" : "text-ink-muted hover:bg-raised"
            }`}
            aria-label="Toggle evidence panel"
            title="Toggle evidence panel"
          >
            <PanelRightOpen size={18} />
          </button>
        </div>
      </header>

      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-3 py-4 sm:space-y-5 sm:px-6 sm:py-5">
        {messages.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="mx-auto flex min-h-full max-w-4xl flex-col items-center justify-start py-2 text-center sm:justify-center sm:py-6"
          >
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-xl bg-brand-gradient bg-[length:160%_160%] shadow-glow motion-safe:animate-gradient-x sm:mb-5 sm:h-16 sm:w-16">
              <Scale size={26} className="text-white sm:h-[30px] sm:w-[30px]" />
            </div>
            <h3 className="max-w-2xl font-display text-2xl font-bold leading-tight text-ink sm:text-4xl">
              Legal answers that separate <span className="gradient-text">knowledge</span> from action.
            </h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted sm:text-[15px]">
              Ask a broad rights question for a clean explanation, or describe what happened for grounded next steps with citations.
            </p>

            <div className="mt-4 grid w-full max-w-3xl gap-2 sm:mt-5 sm:grid-cols-3">
              {FACTS.map((fact) => (
                <span
                  key={fact}
                  className="inline-flex min-h-[42px] items-center justify-center gap-1.5 rounded-lg border border-line bg-raised/80 px-3 py-2 text-xs font-medium text-ink-muted"
                >
                  <BadgeHelp size={13} className="text-accent" />
                  {fact}
                </span>
              ))}
            </div>

            <div className="mt-5 grid w-full gap-2.5 sm:mt-7 sm:grid-cols-2 xl:grid-cols-3">
              {SUGGESTIONS.map((s, i) => (
                <motion.button
                  key={s.q}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + i * 0.05 }}
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.985 }}
                  onClick={() => onSend(s.q)}
                  className="group flex min-h-[88px] items-center gap-3 rounded-lg border border-line bg-panel/80 p-3 text-left text-sm text-ink transition hover:border-brand/50 hover:bg-panel hover:shadow-glow"
                >
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand transition group-hover:scale-105">
                    <s.icon size={18} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                      {s.label}
                    </span>
                    <span className="mt-0.5 block leading-snug">{s.q}</span>
                  </span>
                </motion.button>
              ))}
            </div>
          </motion.div>
        ) : (
          messages.map((m, i) => (
            <MessageBubble
              key={i}
              msg={m}
              streaming={streaming && i === messages.length - 1 && m.role === "assistant"}
            />
          ))
        )}
        <div ref={endRef} />
      </div>

      <Composer onSend={onSend} />
    </section>
  );
}
