"use client";
import { useEffect, useState, useCallback } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { formatMoney, formatDate } from "@/lib/utils";
import { Search, Download, Flag, ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

interface Transaction {
  _id: string;
  description: string;
  transaction_amount: number;
  currency: string;
  direction: string;
  category: string;
  timestamp: string;
  risk_level: string;
  risk_score: number;
  status: string;
  channel: string;
}

type StatusFilter = "all" | "flagged" | "unflagged" | "disputed";

export default function TransactionsPage() {
  const [items, setItems] = useState<Transaction[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [disputing, setDisputing] = useState<string | null>(null);
  const PAGE_SIZE = 25;

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(PAGE_SIZE),
      ...(search ? { search } : {}),
      ...(status !== "all" ? { status } : {}),
    });
    try {
      const d = await apiFetch<{ items: Transaction[]; total: number }>(`/api/transactions?${params}`);
      setItems(d.items ?? []);
      setTotal(d.total ?? 0);
    } finally { setLoading(false); }
  }, [page, search, status]);

  useEffect(() => { load(); }, [load]);

  async function dispute(id: string) {
    setDisputing(id);
    await apiFetch(`/api/transactions/${id}/dispute`, { method: "POST" }).catch(() => {});
    setDisputing(null);
    load();
  }

  async function exportCSV() {
    const params = new URLSearchParams({ ...(search ? { search } : {}), ...(status !== "all" ? { status } : {}) });
    const res = await fetch(`/api/transactions/export?${params}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token") ?? ""}` },
    });
    const blob = await res.blob();
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "statement.csv"; a.click();
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AppLayout>
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="page-title">Transactions</h2>
          <p className="page-desc">{total.toLocaleString()} records</p>
        </div>
        <button onClick={exportCSV} className="btn-secondary">
          <Download className="w-4 h-4" /> Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            type="text" className="input pl-8 py-1.5 text-xs" placeholder="Search description or amount…"
            value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <div className="flex gap-1">
          {(["all","flagged","unflagged","disputed"] as StatusFilter[]).map(s => (
            <button key={s} onClick={() => { setStatus(s); setPage(1); }}
              className={cn("px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                status === s
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              )}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Table — overflow-x-auto for horizontal scroll on small screens */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table min-w-[700px]">
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Category</th>
                <th>Channel</th>
                <th className="text-right">Amount</th>
                <th>Direction</th>
                <th>Risk</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? [...Array(8)].map((_,i) => (
                    <tr key={i}><td colSpan={9}><div className="skeleton h-4 w-full rounded" /></td></tr>
                  ))
                : items.length === 0
                  ? <tr><td colSpan={9} className="text-center text-slate-400 py-10 text-sm">No transactions found.</td></tr>
                  : items.map(t => (
                      <tr key={t._id}>
                        <td className="whitespace-nowrap text-xs">{formatDate(t.timestamp)}</td>
                        <td className="max-w-48 truncate">{t.description}</td>
                        <td>
                          <span className="badge badge-blue text-xs">{t.category || "—"}</span>
                        </td>
                        <td className="text-xs text-slate-400">{t.channel || "—"}</td>
                        <td className={cn("text-right font-medium tabular-nums text-xs", t.direction === "credit" ? "text-emerald-600 dark:text-emerald-400" : "text-slate-700 dark:text-slate-300")}>
                          {t.direction === "credit" ? "+" : "-"}{formatMoney(t.transaction_amount, t.currency)}
                        </td>
                        <td>
                          <span className={cn("badge text-xs", t.direction === "credit" ? "badge-green" : "badge-slate")}>{t.direction}</span>
                        </td>
                        <td>
                          <span className={cn("badge text-xs",
                            t.risk_level === "High" ? "badge-red" : t.risk_level === "Medium" ? "badge-yellow" : "badge-green"
                          )}>{t.risk_level || "Low"}</span>
                        </td>
                        <td>
                          <span className={cn("badge text-xs",
                            t.status === "disputed" ? "badge-yellow" : t.status === "flagged" ? "badge-red" : "badge-slate"
                          )}>{t.status || "normal"}</span>
                        </td>
                        <td>
                          {t.status !== "disputed" && (
                            <button
                              onClick={() => dispute(t._id)}
                              disabled={disputing === t._id}
                              className="btn-ghost p-1.5 text-slate-400 hover:text-amber-600"
                              title="Flag as disputed"
                            >
                              <Flag className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
              }
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-[#1e3352]">
          <span className="text-xs text-slate-400">
            Page {page} of {pages} · {total.toLocaleString()} total
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1} className="btn-ghost p-1.5 disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
            {[...Array(Math.min(5, pages))].map((_, i) => {
              const p = Math.max(1, Math.min(pages - 4, page - 2)) + i;
              return (
                <button key={p} onClick={() => setPage(p)}
                  className={cn("w-7 h-7 text-xs rounded-md font-medium", p === page ? "bg-blue-600 text-white" : "btn-ghost")}
                >{p}</button>
              );
            })}
            <button onClick={() => setPage(p => Math.min(pages, p+1))} disabled={page >= pages} className="btn-ghost p-1.5 disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
