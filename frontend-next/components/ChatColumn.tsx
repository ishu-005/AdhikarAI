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
  "RTI replies usually have a 30-day clock.",
  "Arrested people can ask why they are being arrested.",
  "Consumer complaints can be filed online for many disputes.",
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
    <section className="glass relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl2 border border-line shadow-soft">
      <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
        <div className="flex min-w-0 items-center gap-2">
          <button onClick={onToggleSidebar} className="rounded-lg p-2 text-ink-muted hover:bg-raised md:hidden">
            <Menu size={18} />
          </button>
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 font-display text-base font-semibold text-ink sm:text-lg">
              Legal Assistant
              <span className="hidden items-center gap-1 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-medium text-brand sm:inline-flex">
                <Sparkles size={10} /> cited answers
              </span>
            </h2>
            <p className="truncate text-xs text-ink-muted">
              {contextNotice || "Ask a rights question. Get a cited next step."}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <span className={`flex items-center gap-1.5 rounded-full bg-raised px-2.5 py-1 text-[11px] font-semibold ${st.text}`}>
            <span className="relative flex h-2 w-2">
              {health === "ok" && <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald-400" />}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${st.dot}`} />
            </span>
            <span className="hidden sm:inline">{st.label}</span>
          </span>

          {domain && domain !== "-" && (
            <span className="hidden rounded-full bg-raised px-2.5 py-1 text-[11px] text-ink-muted md:inline">
              {domain.replace(/_/g, " ")}
            </span>
          )}

          <div className="relative flex rounded-xl border border-line bg-raised p-0.5 text-[11px] font-semibold sm:text-xs">
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
                    className="absolute inset-0 -z-10 rounded-lg bg-brand-gradient"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
              </button>
            ))}
          </div>

          <button
            onClick={onToggleInsights}
            className={`rounded-lg p-2 transition ${
              insightsOpen ? "bg-brand-soft text-brand" : "text-ink-muted hover:bg-raised"
            }`}
            aria-label="Toggle evidence panel"
            title="Toggle evidence panel"
          >
            <PanelRightOpen size={18} />
          </button>
        </div>
      </header>

      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto p-3 sm:space-y-5 sm:p-6">
        {messages.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="mx-auto flex min-h-full max-w-3xl flex-col items-center justify-start py-4 text-center sm:justify-center sm:py-6"
          >
            <div className="mb-4 grid h-14 w-14 animate-float place-items-center rounded-2xl bg-brand-gradient shadow-glow sm:mb-5 sm:h-16 sm:w-16 sm:rounded-3xl">
              <Scale size={26} className="text-white sm:h-[30px] sm:w-[30px]" />
            </div>
            <h3 className="max-w-2xl font-display text-xl font-bold text-ink sm:text-3xl">
              Start with the facts. Get your <span className="gradient-text">rights</span> mapped.
            </h3>
            <p className="mt-3 max-w-xl text-sm text-ink-muted">
              Ask in English or Hindi. Short follow-ups like "retry", "explain more", or "in Hindi" now keep the same legal context.
            </p>

            <div className="mt-4 flex max-w-2xl flex-wrap justify-center gap-2 sm:mt-5">
              {FACTS.map((fact) => (
                <span
                  key={fact}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line bg-raised/70 px-3 py-1.5 text-xs text-ink-muted"
                >
                  <BadgeHelp size={13} className="text-accent" />
                  {fact}
                </span>
              ))}
            </div>

            <div className="mt-5 grid w-full gap-2.5 sm:mt-7 sm:grid-cols-2">
              {SUGGESTIONS.map((s, i) => (
                <motion.button
                  key={s.q}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + i * 0.05 }}
                  whileHover={{ y: -2 }}
                  onClick={() => onSend(s.q)}
                  className="group flex min-h-[78px] items-center gap-3 rounded-xl2 border border-line bg-panel/70 p-3 text-left text-sm text-ink transition hover:border-brand/40 hover:bg-panel hover:shadow-glow"
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
