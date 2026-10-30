"use client";
import { useEffect, useRef, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch, apiStream } from "@/lib/api";
import { Send, StopCircle, Plus, Trash2, MessageSquare, FileText, ExternalLink, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Doc { id: string; name: string; chunk_count: number; }
interface Message { role: "user"|"assistant"; content: string; sources?: Source[]; }
interface Source { citation: number; document_id: string; snippet: string; page?: number; section?: string; content_type: string; original?: string; }
interface Conversation { conversation_id: string; title: string; message_count: number; updated_at: string; }

export default function RagPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [scope, setScope] = useState("all");
  const [messages, setMessages] = useState<Message[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [convList, setConvList] = useState<Conversation[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const scroll = () => setTimeout(() => threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" }), 50);

  useEffect(() => {
    apiFetch<{ documents: Doc[] }>("/api/rag/documents").then(d => setDocs(d.documents ?? [])).catch(() => {});
    loadConvs();
  }, []);

  function loadConvs() {
    apiFetch<{ conversations: Conversation[] }>("/api/rag/conversations").then(d => setConvList(d.conversations ?? [])).catch(() => {});
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (busy) { abortRef.current?.abort(); return; }
    const q = query.trim(); if (!q) return;
    setQuery(""); setError(""); setStage(""); setStreamText("");
    setBusy(true);
    setMessages(prev => [...prev, { role: "user", content: q }]);
    scroll();
    const ac = new AbortController(); abortRef.current = ac;
    try {
      const result = await apiStream(
        "/api/rag/ask/stream",
        { query: q, document_id: scope, conversation_id: convId },
        s => { setStage(s); scroll(); },
        t => { setStreamText(prev => prev + t); scroll(); },
        ac.signal
      );
      setMessages(prev => [...prev, { role: "assistant", content: result.answer, sources: result.sources as Source[] }]);
      if (result.conversation_id) setConvId(result.conversation_id);
      setStreamText(""); setStage("");
      loadConvs();
    } catch (ex: unknown) {
      if ((ex as Error).name !== "AbortError") setError((ex as Error).message ?? "Error");
      setStreamText(""); setStage("");
    } finally { setBusy(false); scroll(); }
  }

  async function openConversation(id: string) {
    const d = await apiFetch<{ messages: Array<{role:string; content:string; payload?: { answer:string; sources?: Source[] }}>; scope?: string }>(`/api/rag/conversations/${id}`);
    setMessages(d.messages.map(m => m.role === "assistant"
      ? { role: "assistant", content: m.payload?.answer ?? m.content, sources: m.payload?.sources }
      : { role: "user", content: m.content }
    ));
    setConvId(id);
    if (d.scope && (d.scope === "all" || docs.find(doc => doc.id === d.scope))) setScope(d.scope);
    scroll();
  }

  async function deleteConv(id: string) {
    await apiFetch(`/api/rag/conversations/${id}`, { method: "DELETE" }).catch(() => {});
    if (convId === id) { setMessages([]); setConvId(null); }
    loadConvs();
  }

  async function openOriginal(source: Source) {
    const d = await apiFetch<{ url: string; kind: string }>(`/api/rag/documents/${source.document_id}/open`, { method: "POST" });
    const url = d.kind === "pdf" ? `${d.url}${source.page ? `#page=${source.page}` : ""}` : d.url;
    window.open(url, "_blank", "noopener");
  }

  return (
    <AppLayout>
      <div className="flex h-[calc(100vh-3.5rem-2.5rem)] gap-4">
        {/* Sidebar */}
        <aside className="w-52 shrink-0 flex flex-col gap-3">
          <div className="card p-3">
            <label className="label">Document</label>
            <select className="input text-xs" value={scope} onChange={e => setScope(e.target.value)}>
              <option value="all">All documents</option>
              <option value="">Gemini only</option>
              {docs.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <button onClick={() => { setMessages([]); setConvId(null); }} className="btn-secondary text-xs py-1.5">
            <Plus className="w-3.5 h-3.5" /> New chat
          </button>
          <div className="card p-3 flex-1 overflow-hidden flex flex-col min-h-0">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">Recent chats</p>
            <div className="overflow-y-auto space-y-1 flex-1">
              {convList.length === 0 ? <p className="text-xs text-slate-400 text-center py-4">No saved chats</p>
                : convList.map(c => (
                    <div key={c.conversation_id} className={cn("flex items-center gap-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800/60 group", convId === c.conversation_id && "bg-blue-50 dark:bg-blue-900/20")}>
                      <button onClick={() => openConversation(c.conversation_id)} className="flex-1 text-left px-2 py-1.5 min-w-0">
                        <p className="text-xs truncate text-slate-700 dark:text-slate-300">{c.title || "Untitled"}</p>
                        <p className="text-xs text-slate-400">{Math.ceil((c.message_count||0)/2)} q</p>
                      </button>
                      <button onClick={() => deleteConv(c.conversation_id)} className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-opacity">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
            </div>
          </div>
        </aside>

        {/* Chat */}
        <div className="flex-1 flex flex-col min-w-0 card overflow-hidden">
          {/* Thread */}
          <div ref={threadRef} className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && !busy && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <MessageSquare className="w-10 h-10 text-slate-300 dark:text-slate-600 mb-3" />
                <p className="text-sm font-medium text-slate-500 dark:text-slate-400">Ask anything about your documents</p>
                <p className="text-xs text-slate-400 mt-1">Select a document or use "All documents"</p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className={cn("max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed",
                  m.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 dark:bg-[#1a2740] text-slate-800 dark:text-slate-200"
                )}>
                  <p className="whitespace-pre-wrap">{m.content}</p>
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-200 dark:border-[#1e3352] space-y-1">
                      {m.sources.slice(0, 4).map((s, j) => (
                        <div key={j} className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">[{s.citation}] {s.section || "Source"}{s.page ? ` · p.${s.page}` : ""}</p>
                          </div>
                          {s.original && (
                            <button onClick={() => openOriginal(s)} className="shrink-0 text-blue-600 hover:text-blue-700 dark:text-blue-400">
                              <ExternalLink className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-xl px-4 py-2.5 bg-slate-100 dark:bg-[#1a2740] text-sm">
                  {stage && <p className="text-xs text-blue-600 dark:text-blue-400 mb-1 animate-pulse">{stage}…</p>}
                  {streamText
                    ? <p className="text-slate-800 dark:text-slate-200 whitespace-pre-wrap">{streamText}</p>
                    : <div className="flex gap-1">{[0,1,2].map(i => <div key={i} className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
                  }
                </div>
              </div>
            )}
            {error && <p className="text-xs text-red-600 text-center">{error}</p>}
          </div>

          {/* Input */}
          <form onSubmit={ask} className="border-t border-slate-200 dark:border-[#1e3352] p-3 flex gap-2">
            <input
              type="text" className="input flex-1" placeholder="Ask about the document…"
              value={query} onChange={e => setQuery(e.target.value)} disabled={false}
            />
            <button type="submit" className={cn("btn-primary px-3", busy && "bg-red-600 hover:bg-red-700")} aria-label={busy ? "Stop" : "Send"}>
              {busy ? <StopCircle className="w-4 h-4" /> : <Send className="w-4 h-4" />}
            </button>
          </form>
        </div>
      </div>
    </AppLayout>
  );
}
