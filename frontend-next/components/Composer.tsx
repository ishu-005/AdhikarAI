"use client";

import { useRef, useState } from "react";
import { CornerDownLeft, Loader2, Send } from "lucide-react";
import { motion } from "framer-motion";
import { useChat } from "@/lib/store";

const MAX = 4000;

export default function Composer({ onSend }: { onSend: (q: string) => void }) {
  const [value, setValue] = useState("");
  const { streaming } = useChat();
  const ref = useRef<HTMLTextAreaElement>(null);

  const grow = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  };

  const submit = () => {
    if (!value.trim() || streaming) return;
    onSend(value);
    setValue("");
    requestAnimationFrame(() => {
      if (ref.current) ref.current.style.height = "auto";
    });
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-line bg-panel/60 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] sm:p-4">
      <div className="group relative rounded-xl2 border border-line bg-raised transition focus-within:border-brand/50 focus-within:shadow-glow">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => {
            setValue(e.target.value.slice(0, MAX));
            grow();
          }}
          onKeyDown={onKey}
          placeholder="Describe the facts or ask a follow-up like retry, explain more, or in Hindi"
          className="scroll-thin block max-h-[180px] w-full resize-none bg-transparent px-4 py-3 pr-14 text-[15px] text-ink outline-none placeholder:text-ink-muted/70"
        />
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={submit}
          disabled={streaming || !value.trim()}
          aria-label="Send"
          className="absolute bottom-2.5 right-2.5 grid h-9 w-9 place-items-center rounded-xl bg-brand-gradient text-white shadow-glow transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
        >
          {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </motion.button>
      </div>

      <div className="mt-2 flex items-center justify-between gap-2 px-1 text-[11px] text-ink-muted">
        <span className="hidden items-center gap-1.5 sm:flex">
          <kbd className="rounded border border-line bg-raised px-1.5 py-0.5 font-sans">Enter</kbd>
          to send
          <span className="mx-1 opacity-40">/</span>
          <kbd className="rounded border border-line bg-raised px-1.5 py-0.5 font-sans inline-flex items-center gap-1">
            <CornerDownLeft size={10} /> Shift+Enter
          </kbd>
          newline
        </span>
        <span className={value.length > MAX - 200 ? "text-amber-500" : ""}>
          {value.length}/{MAX}
        </span>
      </div>
    </div>
  );
}
