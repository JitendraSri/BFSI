"use client";
import { useState, useEffect } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { cn, formatMoney } from "@/lib/utils";
import { Loader2, RefreshCw, Info } from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

interface ScoreResult { fraud_score: number; anomaly_score: number; hybrid_risk: number; risk_level: string; reasons: string[]; }
interface MetricsData { can_retrain: boolean; metrics_history: Array<{ timestamp: string; fraud_f1: number; roc_auc: number }>; }

const CHANNELS = ["UPI", "NEFT", "IMPS", "POS", "ATM", "Online", "NACH"];
const CATS = ["food", "groceries", "transport", "entertainment", "utilities", "shopping", "travel", "loan", "salary", "transfer"];

export default function PredictivePage() {
  const [amount, setAmount] = useState(5000);
  const [channel, setChannel] = useState("UPI");
  const [category, setCategory] = useState("food");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [metricsData, setMetricsData] = useState<MetricsData | null>(null);
  const [retraining, setRetraining] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    apiFetch<MetricsData>("/api/metrics-history").then(setMetricsData).catch(() => {});
  }, []);

  async function simulate(e: React.FormEvent) {
    e.preventDefault(); setLoading(true);
    try {
      const d = await apiFetch<ScoreResult>("/api/predict-risk", {
        method: "POST", body: JSON.stringify({ transaction_amount: amount, channel, category, direction: "debit" }),
      });
      setResult(d);
    } finally { setLoading(false); }
  }

  async function retrain() {
    setRetraining(true);
    try {
      const d = await apiFetch<{ message: string; seconds: number }>("/api/retrain", { method: "POST" });
      setMsg(`Retrained in ${d.seconds?.toFixed(1)}s.`);
      apiFetch<MetricsData>("/api/metrics-history").then(setMetricsData).catch(() => {});
    } catch (ex: unknown) { setMsg(ex instanceof Error ? ex.message : "Failed"); }
    finally { setRetraining(false); setTimeout(() => setMsg(""), 4000); }
  }

  const riskColor = result
    ? result.risk_level === "High" ? "text-red-600" : result.risk_level === "Medium" ? "text-amber-600" : "text-emerald-600"
    : "";

  return (
    <AppLayout>
      <div className="page-header"><h2 className="page-title">Predictive Modeling</h2><p className="page-desc">Simulate transaction risk and manage model retraining</p></div>

      {msg && <p className="mb-4 text-xs text-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-400 px-3 py-2 rounded-lg">{msg}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        {/* Simulator */}
        <div className="card p-4">
          <h3 className="section-title">Risk Simulator</h3>
          <form onSubmit={simulate} className="space-y-3">
            <div><label className="label">Amount (₹)</label><input type="number" className="input" min={1} value={amount} onChange={e => setAmount(Number(e.target.value))} /></div>
            <div>
              <label className="label">Channel</label>
              <select className="input" value={channel} onChange={e => setChannel(e.target.value)}>
                {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Category</label>
              <select className="input" value={category} onChange={e => setCategory(e.target.value)}>
                {CATS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase()+c.slice(1)}</option>)}
              </select>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Simulate"}</button>
          </form>
        </div>

        {/* Result */}
        <div className="card p-4">
          <h3 className="section-title">Result</h3>
          {result ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "Fraud Score", value: result.fraud_score },
                  { label: "Anomaly Score", value: result.anomaly_score },
                  { label: "Hybrid Risk", value: result.hybrid_risk },
                ].map(s => (
                  <div key={s.label} className="stat-card p-3">
                    <span className="stat-label">{s.label}</span>
                    <span className={cn("stat-value text-lg", riskColor)}>{Math.round(s.value)}</span>
                  </div>
                ))}
              </div>
              <div className={cn("badge text-sm px-3 py-1.5", result.risk_level === "High" ? "badge-red" : result.risk_level === "Medium" ? "badge-yellow" : "badge-green")}>
                Risk Level: {result.risk_level}
              </div>
              {result.reasons.length > 0 && (
                <div className="space-y-1.5">
                  {result.reasons.map((r, i) => (
                    <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-slate-50 dark:bg-[#1a2740]">
                      <Info className="w-3.5 h-3.5 text-amber-600 mt-0.5 shrink-0" />
                      <p className="text-xs text-slate-600 dark:text-slate-400">{r}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : <p className="text-xs text-slate-400 text-center py-12">Run a simulation to see results.</p>}
        </div>
      </div>

      {/* Model history */}
      {metricsData?.metrics_history && metricsData.metrics_history.length > 0 && (
        <div className="card p-4 mb-4">
          <p className="section-title">Training History</p>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={metricsData.metrics_history} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="timestamp" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5,10)} />
              <YAxis tick={{ fontSize: 10 }} domain={[0,1]} />
              <Tooltip contentStyle={{ fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="fraud_f1" name="Fraud F1" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="roc_auc" name="ROC-AUC" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {metricsData?.can_retrain && (
        <button onClick={retrain} disabled={retraining} className="btn-secondary">
          {retraining ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Retrain models
        </button>
      )}
    </AppLayout>
  );
}
