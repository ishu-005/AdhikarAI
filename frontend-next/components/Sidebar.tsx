"use client";

import { Plus, Scale, Trash2, X, MessagesSquare } from "lucide-react";
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
      {/* Mobile backdrop */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-20 bg-black/40 backdrop-blur-sm md:hidden"
          />
        )}
      </AnimatePresence>

      <aside
        className={`${
          open ? "translate-x-0" : "-translate-x-[110%]"
        } fixed inset-y-0 left-0 z-30 w-72 transform p-3 transition-transform duration-300 md:static md:translate-x-0`}
      >
        <div className="glass flex h-full flex-col rounded-xl2 border border-line p-4 shadow-soft">
          {/* Brand */}
          <div className="mb-5 flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-brand-gradient shadow-glow">
                <Scale size={22} className="text-white" />
              </div>
              <div>
                <h1 className="font-display text-xl font-bold leading-none text-ink">
                  Adhikar<span className="gradient-text">AI</span>
                </h1>
                <p className="mt-1 text-[11px] text-ink-muted">Know your rights · हिंदी & English</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={onClose} className="rounded-lg p-2 text-ink-muted md:hidden" aria-label="Close">
                <X size={16} />
              </button>
            </div>
          </div>

          {/* New chat */}
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={onNewChat}
            className="group mb-5 flex items-center justify-center gap-2 rounded-xl bg-brand-gradient px-4 py-3 text-sm font-semibold text-white shadow-glow transition hover:brightness-110"
          >
            <Plus size={17} className="transition-transform group-hover:rotate-90" /> New chat
          </motion.button>

          <div className="mb-2 flex items-center gap-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            <MessagesSquare size={13} /> Recent chats
          </div>

          <ul className="scroll-thin -mx-1 flex-1 space-y-1 overflow-y-auto px-1">
            {threads.length === 0 && (
              <li className="rounded-lg px-3 py-6 text-center text-sm text-ink-muted">
                No conversations yet.
                <br />
                Ask your first question →
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
                        active
                          ? "bg-brand-soft text-ink"
                          : "text-ink-muted hover:bg-raised hover:text-ink"
                      }`}
                    >
                      {active && (
                        <motion.span
                          layoutId="active-thread"
                          className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand-gradient"
                        />
                      )}
                      <span className="truncate">{t.title || "Untitled"}</span>
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

          {/* Footer */}
          <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
            <span className="text-[11px] text-ink-muted">Theme</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>
    </>
  );
}
