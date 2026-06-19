"use client";

import { MessagesSquare, Plus, Scale, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "@/lib/api";
import { useChat } from "@/lib/store";
import ThemeToggle from "./ThemeToggle";

export default function Sidebar({
  open,
  onClose,
  onNewChat,
  onOpenThread,
}: {
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onOpenThread: (id: string) => void;
}) {
  const { threads, activeId, removeThread, setActive, setMessages } = useChat();

  const del = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.deleteChat(id).catch(() => {});
    removeThread(id);
    if (activeId === id) {
      setActive(null);
      setMessages([]);
    }
  };

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-20 bg-ink/35 backdrop-blur-sm md:hidden"
          />
        )}
      </AnimatePresence>

      <aside
        className={`${
          open ? "translate-x-0" : "-translate-x-[110%]"
        } fixed inset-y-0 left-0 z-30 w-[min(19rem,calc(100vw-1rem))] transform p-2 transition-transform duration-300 sm:p-3 md:static md:w-[18.5rem] md:translate-x-0 lg:w-[19.5rem]`}
      >
        <div className="glass flex h-full flex-col rounded-xl2 border border-line p-3 shadow-panel sm:p-4">
          <div className="mb-4 flex items-start justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-gradient bg-[length:160%_160%] shadow-glow motion-safe:animate-gradient-x">
                <Scale size={22} className="text-white" />
              </div>
              <div className="min-w-0">
                <h1 className="truncate font-display text-xl font-bold leading-none text-ink">
                  Adhikar<span className="gradient-text">AI</span>
                </h1>
                <p className="mt-1 text-[11px] font-medium text-ink-muted">Rights guidance in Hindi & English</p>
              </div>
            </div>
            <button onClick={onClose} className="rounded-lg p-2 text-ink-muted hover:bg-raised md:hidden" aria-label="Close">
              <X size={16} />
            </button>
          </div>

          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={onNewChat}
            className="group mb-4 flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-brand-gradient bg-[length:160%_160%] px-4 py-3 text-sm font-semibold text-white shadow-glow transition hover:brightness-110 motion-safe:animate-gradient-x"
          >
            <Plus size={17} className="transition-transform group-hover:rotate-90" /> New chat
          </motion.button>

          <div className="mb-2 flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            <span className="flex items-center gap-2">
              <MessagesSquare size={13} /> Recent chats
            </span>
            <span className="rounded-md bg-raised px-1.5 py-0.5 text-[10px]">{threads.length}</span>
          </div>

          <ul className="scroll-thin -mx-1 flex-1 space-y-1 overflow-y-auto px-1">
            {threads.length === 0 && (
              <li className="rounded-lg border border-dashed border-line bg-raised/60 px-3 py-6 text-center text-sm text-ink-muted">
                No conversations yet.
                <br />
                Ask your first question
              </li>
            )}
            <AnimatePresence initial={false}>
              {threads.map((t) => {
                const active = activeId === t.id;
                return (
                  <motion.li
                    key={t.id}
                    layout
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <button
                      onClick={() => onOpenThread(t.id)}
                      className={`group relative flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                        active ? "bg-brand-soft text-ink shadow-soft" : "text-ink-muted hover:bg-raised hover:text-ink"
                      }`}
                    >
                      {active && (
                        <motion.span
                          layoutId="active-thread"
                          className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand-gradient"
                        />
                      )}
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{t.title || "Untitled"}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-ink-muted">
                          {(t.domain || "general").replace(/_/g, " ")}
                        </span>
                      </span>
                      <span
                        onClick={(e) => del(t.id, e)}
                        className="shrink-0 rounded-md p-1 opacity-0 transition hover:bg-red-500/10 hover:text-red-500 group-hover:opacity-100"
                      >
                        <Trash2 size={14} />
                      </span>
                    </button>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>

          <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
            <span className="text-[11px] text-ink-muted">Theme</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>
    </>
  );
}
