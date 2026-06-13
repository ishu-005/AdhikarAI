"use client";

import { useState } from "react";
import { BookMarked, ChevronDown, ExternalLink, FileText, Globe, Upload, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "@/lib/api";
import { useChat } from "@/lib/store";
import type { DynamicSource } from "@/lib/types";

function Section({
  title,
  icon,
  count,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  count?: number;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <section className="border-b border-line">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-ink transition hover:bg-raised/50"
      >
        <span className="flex items-center gap-2">
          <span className="text-brand">{icon}</span>
          {title}
        </span>
        <span className="flex items-center gap-2 text-ink-muted">
          {count !== undefined && (
            <span className="min-w-5 rounded-full bg-brand-soft px-1.5 py-0.5 text-center text-[11px] font-semibold text-brand">
              {count}
            </span>
          )}
          <ChevronDown size={15} className={`transition-transform ${open ? "" : "-rotate-90"}`} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

export default function InsightsPanel({
  domains,
  sources,
  onClose,
}: {
  domains: string[];
  sources: DynamicSource[];
  onClose: () => void;
}) {
  const { citations, liveSources } = useChat();
  const [uploadDomain, setUploadDomain] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const upload = async () => {
    if (!file || !uploadDomain) {
      setStatus("Pick a domain and a PDF file.");
      return;
    }
    setBusy(true);
    setStatus("Uploading…");
    try {
      const res = await api.uploadPdf(uploadDomain, file);
      setStatus(`✓ ${res.filename} — ingest ${res.ingest_status}.`);
      setFile(null);
    } catch (e: any) {
      setStatus(`Upload failed: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="glass fixed inset-x-2 bottom-2 top-2 z-40 flex flex-col overflow-hidden rounded-xl2 border border-line shadow-soft sm:inset-x-auto sm:right-3 sm:w-80 lg:static lg:z-auto">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <h2 className="font-display text-base font-semibold text-ink">Insight Box</h2>
          <p className="text-xs text-ink-muted">Citations, sources, and uploads</p>
        </div>
        <button onClick={onClose} className="rounded-lg p-1.5 text-ink-muted hover:bg-raised" aria-label="Hide">
          <X size={16} />
        </button>
      </div>

      <div className="scroll-thin flex-1 overflow-y-auto">
        <Section title="Citations" icon={<BookMarked size={15} />} count={citations.length}>
          {citations.length === 0 ? (
            <p className="rounded-lg bg-raised/60 px-3 py-4 text-center text-sm text-ink-muted">
              Citations from the bare acts will appear here.
            </p>
          ) : (
            <ul className="space-y-2">
              {citations.map((c, i) => (
                <motion.li
                  key={c.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="rounded-xl border border-line bg-raised/70 p-3 text-sm transition hover:border-brand/40"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium leading-snug text-ink">
                      <span className="text-brand">[{c.id}]</span> {c.section}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-ink-muted">{c.source}</p>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className="inline-block rounded-md bg-brand-soft px-1.5 py-0.5 text-[10px] font-medium text-brand">
                      {(c.domain || "general").replace(/_/g, " ")}
                    </span>
                    {c.score != null && (
                      <span className="flex items-center gap-1.5">
                        <span className="h-1.5 w-12 overflow-hidden rounded-full bg-line">
                          <span
                            className="block h-full rounded-full bg-brand-gradient"
                            style={{ width: `${Math.min(100, Math.max(8, c.score * 100))}%` }}
                          />
                        </span>
                        <span className="text-[10px] tabular-nums text-ink-muted">{c.score}</span>
                      </span>
                    )}
                  </div>
                </motion.li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Live web sources" icon={<Globe size={15} />} count={liveSources.length}>
          {liveSources.length === 0 ? (
            <p className="rounded-lg bg-raised/60 px-3 py-4 text-center text-sm text-ink-muted">
              No live sources fetched for this query.
            </p>
          ) : (
            <ul className="space-y-2">
              {liveSources.map((s, i) => (
                <li key={i} className="rounded-xl border border-line bg-raised/70 p-3 text-sm">
                  <a href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-medium text-brand hover:underline">
                    {s.label} <ExternalLink size={12} />
                  </a>
                  <p className="mt-1 line-clamp-3 text-xs text-ink-muted">{s.snippet}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Configured sources" icon={<FileText size={15} />} count={sources.length}>
          <ul className="space-y-1.5">
            {sources.map((s, i) => (
              <li key={i} className="flex items-center justify-between gap-2 text-sm">
                <a href={s.url} target="_blank" rel="noreferrer" className="truncate text-ink-muted hover:text-brand">
                  {s.label}
                </a>
                <span
                  className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                    s.enabled === false ? "bg-red-500/10 text-red-400" : "bg-emerald-500/10 text-emerald-500"
                  }`}
                >
                  {s.enabled === false ? "off" : "on"}
                </span>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Upload a PDF" icon={<Upload size={15} />}>
          <div className="space-y-2.5">
            <select
              value={uploadDomain}
              onChange={(e) => setUploadDomain(e.target.value)}
              className="w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink outline-none focus:border-brand/50"
            >
              <option value="">Select legal domain…</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d.replace(/_/g, " ")}
                </option>
              ))}
            </select>

            <label className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-line bg-raised/50 px-3 py-5 text-center text-xs text-ink-muted transition hover:border-brand/50 hover:bg-brand-soft/30">
              <Upload size={18} className="text-brand" />
              {file ? <span className="font-medium text-ink">{file.name}</span> : "Click to choose a PDF"}
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="hidden"
              />
            </label>

            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={upload}
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-gradient px-3 py-2 text-sm font-semibold text-white shadow-glow transition hover:brightness-110 disabled:opacity-50"
            >
              <Upload size={15} /> {busy ? "Uploading…" : "Upload & ingest"}
            </motion.button>
            {status && <p className="text-xs text-ink-muted">{status}</p>}
          </div>
        </Section>
      </div>
    </aside>
  );
}
