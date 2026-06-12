"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Scale, User } from "lucide-react";
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.21, 1.02, 0.73, 1] }}
      className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* Avatar */}
      <div
        className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl shadow-soft ${
          isUser ? "bg-raised text-ink-muted" : "bg-brand-gradient text-white"
        }`}
      >
        {isUser ? <User size={15} /> : <Scale size={15} />}
      </div>

      {/* Bubble */}
      <div className={`group relative max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-xl2 px-4 py-3 text-[15px] shadow-soft ${
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

        {/* Copy button (assistant, when there is content) */}
        {!isUser && msg.content && !streaming && (
          <button
            onClick={copy}
            className="absolute -bottom-2 right-1 flex items-center gap-1 rounded-lg border border-line bg-panel px-2 py-1 text-[11px] text-ink-muted opacity-0 shadow-soft transition hover:text-ink group-hover:opacity-100"
          >
            {copied ? <Check size={12} className="text-accent" /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
    </motion.div>
  );
}
