"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, BookOpenText, Check, Copy, Database, Globe2, RotateCcw, Scale, ShieldCheck, User } from "lucide-react";
import { motion } from "framer-motion";
import type { ChatMessage } from "@/lib/types";

export default function MessageBubble({ msg, streaming }: { msg: ChatMessage; streaming?: boolean }) {
  const isUser = msg.role === "user";
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  const empty = !msg.content && streaming;
  const diagnostics = !isUser ? msg.meta?.diagnostics : undefined;
  const issueCount = diagnostics?.issues?.length ?? 0;
  const answerStyle = diagnostics?.answer_style;
  const confidence = diagnostics?.source_confidence;
  const confidenceTone =
    confidence?.level === "strong"
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300"
      : confidence?.level === "web_fallback"
        ? "border-accent/30 bg-accent/10 text-accent"
        : confidence?.level === "missing"
          ? "border-red-500/20 bg-red-500/10 text-red-500"
          : "border-amber-500/25 bg-amber-500/10 text-amber-600 dark:text-amber-300";
  const ConfidenceIcon =
    confidence?.level === "strong"
      ? ShieldCheck
      : confidence?.level === "web_fallback"
        ? Globe2
        : AlertTriangle;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.21, 1.02, 0.73, 1] }}
      className={`flex items-start gap-2 sm:gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      <div
        className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg shadow-soft ${
          isUser ? "bg-raised text-ink-muted" : "bg-brand-gradient text-white"
        }`}
      >
        {isUser ? <User size={15} /> : <Scale size={15} />}
      </div>

      <div className={`group relative max-w-[calc(100%-2.75rem)] sm:max-w-[82%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-xl2 px-3.5 py-3 text-[15px] shadow-soft sm:px-4 ${
            isUser
              ? "rounded-tr-md bg-brand-gradient text-white"
              : "rounded-tl-md border border-line bg-panel text-ink"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
          ) : empty ? (
            <div className="space-y-2 py-1">
              <div className="shimmer h-3 w-40" />
              <div className="shimmer h-3 w-56" />
              <div className="shimmer h-3 w-32" />
            </div>
          ) : (
            <div className={`prose-chat ${streaming ? "cursor-blink" : ""}`}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ""}</ReactMarkdown>
            </div>
          )}
        </div>

        {!isUser && diagnostics && !empty && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-muted">
            {diagnostics.needs_retrieval !== false ? (
              <span className="inline-flex items-center gap-1 rounded-md border border-line bg-raised px-2 py-1">
                <Database size={12} />
                RAG used
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-md border border-line bg-raised px-2 py-1">
                <BookOpenText size={12} />
                Chat only
              </span>
            )}
            {answerStyle === "educational" && (
              <span className="inline-flex items-center gap-1 rounded-md border border-line bg-brand-soft px-2 py-1 font-medium text-brand">
                <BookOpenText size={12} />
                Educational
              </span>
            )}
            {confidence?.label && (
              <span
                title={confidence.reason}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 font-medium ${confidenceTone}`}
              >
                <ConfidenceIcon size={12} />
                {confidence.label}
              </span>
            )}
            {diagnostics.query_type && (
              <span className="rounded-md border border-line bg-raised px-2 py-1">
                {diagnostics.query_type.replaceAll("_", " ")}
              </span>
            )}
            {issueCount > 1 && (
              <span className="rounded-md border border-line bg-raised px-2 py-1">{issueCount} issues</span>
            )}
            {(diagnostics.retrieval_count ?? 0) > 0 && (
              <span className="rounded-md border border-line bg-raised px-2 py-1">
                {diagnostics.retrieval_count} chunks
              </span>
            )}
            {diagnostics.rewritten && (
              <span className="inline-flex items-center gap-1 rounded-md border border-line bg-raised px-2 py-1">
                <RotateCcw size={12} />
                Follow-up
              </span>
            )}
          </div>
        )}

        {!isUser && msg.content && !streaming && (
          <button
            onClick={copy}
            className="absolute -bottom-2 right-1 flex items-center gap-1 rounded-lg border border-line bg-panel px-2 py-1 text-[11px] text-ink-muted opacity-100 shadow-soft transition hover:text-ink sm:opacity-0 sm:group-hover:opacity-100"
          >
            {copied ? <Check size={12} className="text-accent" /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
    </motion.div>
  );
}
