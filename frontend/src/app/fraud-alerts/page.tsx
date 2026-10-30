"use client";
import { useEffect, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { formatMoney, formatDate } from "@/lib/utils";
import { ShieldAlert, ShieldCheck, RefreshCw, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";

interface Alert { id: string; description: string; transaction_amount: number; currency: string; risk_score: number; risk_level: string; timestamp: string; status: string; reasons: string[]; verdict?: string; channel: string; }

export default function FraudAlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    apiFetch<{ alerts: Alert[] }>("/api/alerts").then(d => setAlerts(d.alerts ?? [])).finally(() => setLoading(false));
  };
  useEffect(load, []);

  async function review(id: string, verdict: string) {
    setActing(id);
    await apiFetch(`/api/alerts/${id}/review`, { method: "POST", body: JSON.stringify({ verdict }) }).catch(() => {});
    setActing(null);
    load();
  }

  return (
    <AppLayout>
      <div className="page-header">
        <h2 className="page-title">Fraud Alerts</h2>
        <p className="page-desc">Review AI-flagged transactions and label them to improve the model</p>
      </div>

      {loading ? (
        <div className="space-y-3">{[...Array(4)].map((_,i) => <div key={i} className="skeleton h-24 rounded-xl" />)}</div>
      ) : alerts.length === 0 ? (
        <div className="card p-12 text-center">
          <ShieldCheck className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">No open alerts</p>
          <p className="text-xs text-slate-400 mt-1">Import transactions to begin fraud analysis.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map(a => (
            <div key={a.id} className="card p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    a.risk_level === "High" ? "bg-red-100 dark:bg-red-900/30" : "bg-amber-100 dark:bg-amber-900/30"
                  )}>
                    <ShieldAlert className={cn("w-4 h-4", a.risk_level === "High" ? "text-red-600" : "text-amber-600")} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{a.description}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{formatDate(a.timestamp)} · {a.channel}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {a.reasons.map((r, i) => <span key={i} className="badge badge-slate">{r}</span>)}
                    </div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-base font-semibold text-slate-900 dark:text-slate-100 tabular-nums">{formatMoney(a.transaction_amount, a.currency)}</p>
                  <p className={cn("text-xs font-medium mt-0.5",
                    a.risk_level === "High" ? "text-red-600" : "text-amber-600"
                  )}>Risk {a.risk_score}/100</p>
                </div>
              </div>

              {a.verdict ? (
                <div className="mt-3 flex items-center gap-2">
                  <span className={cn("badge", a.verdict === "fraud" ? "badge-red" : a.verdict === "legitimate" ? "badge-green" : "badge-yellow")}>
                    {a.verdict}
                  </span>
                  <button onClick={() => review(a.id, "reopen")} disabled={acting === a.id} className="btn-ghost py-1 px-2 text-xs">
                    <RotateCcw className="w-3 h-3" /> Reopen
                  </button>
                </div>
              ) : (
                <div className="mt-3 flex gap-2">
                  <button onClick={() => review(a.id, "legitimate")} disabled={acting === a.id} className="btn-secondary py-1.5 text-xs flex-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Legitimate
                  </button>
                  <button onClick={() => review(a.id, "fraud")} disabled={acting === a.id} className="btn-danger py-1.5 text-xs flex-1">
                    <ShieldAlert className="w-3.5 h-3.5" /> Fraud
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </AppLayout>
  );
}
