"use client";
import { useEffect, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { Info, Database, Shield, Zap } from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, BarChart, Bar } from "recharts";

interface Metrics { roc_auc: number; pr_auc: number; fraud_precision: number; fraud_recall: number; fraud_f1: number; fpr: number; }
interface InsightData {
  fraud_model_metrics?: Metrics;
  anomaly_metrics?: Metrics;
  metrics_history?: Array<{ timestamp: string; fraud_f1: number; roc_auc: number }>;
  confusion_matrix?: number[][];
  finrag_results?: { recall_at_k?: number; mrr?: number; ndcg?: number };
}

const DATASETS = [
  {
    name: "Transaction Data (10,061 records)",
    icon: Database,
    color: "blue",
    feature: "Fraud Detection & Anomaly Detection",
    how: "Labelled debit/credit transactions from MongoDB. Random Forest classifier trained on 15 features (amount, channel, account age, velocity). Isolation Forest trained unsupervised on transaction vectors. Labels from user reviews (mark Legitimate/Fraud) retrain the model.",
  },
  {
    name: "FinanceBench (150 QA pairs)",
    icon: Zap,
    color: "purple",
    feature: "FinRAG Copilot Evaluation",
    how: "150 analyst questions over real 10-K/10-Q filings with annotated answers and evidence pages. Used to measure end-to-end RAG quality (claim precision, recall, grounding). Download via: python app.py download-datasets.",
  },
  {
    name: "FinDER (5,703 QA triplets)",
    icon: Database,
    color: "indigo",
    feature: "FinRAG Retrieval Evaluation",
    how: "Expert-annotated query/evidence/answer triplets from SEC 10-Ks. Short, jargon-heavy queries. Measures whether the exact evidence passage is retrieved. Retrieval Recall@7, MRR and nDCG@10 reported on Insights.",
  },
  {
    name: "SEC EDGAR (48 bundled 10-Ks)",
    icon: Shield,
    color: "slate",
    feature: "FinRAG Copilot — Knowledge Base",
    how: "Real SEC filings pre-indexed at startup. Chunked using table-aware parsing, embedded with Gemini gemini-embedding-001, stored as NumPy float32 arrays. Hybrid sparse+dense retrieval with RRF fusion.",
  },
];

export default function InsightsPage() {
  const [data, setData] = useState<InsightData | null>(null);
  useEffect(() => {
    apiFetch<InsightData>("/api/metrics").then(setData).catch(() => {});
  }, []);

  const m = data?.fraud_model_metrics;

  return (
    <AppLayout>
      <div className="page-header">
        <h2 className="page-title">Insights</h2>
        <p className="page-desc">Model performance, benchmarks, datasets and FinRAG vs other AI tools</p>
      </div>

      {/* Model metrics */}
      {m && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
          {[
            { label: "ROC-AUC", value: m.roc_auc?.toFixed(3) },
            { label: "PR-AUC", value: m.pr_auc?.toFixed(3) },
            { label: "Fraud F1", value: m.fraud_f1?.toFixed(3) },
            { label: "Fraud Precision", value: m.fraud_precision?.toFixed(3) },
            { label: "Fraud Recall", value: m.fraud_recall?.toFixed(3) },
            { label: "False Positive Rate", value: m.fpr?.toFixed(3) },
          ].map(s => (
            <div key={s.label} className="stat-card">
              <span className="stat-label">{s.label}</span>
              <span className="stat-value text-blue-700 dark:text-blue-300">{s.value ?? "—"}</span>
            </div>
          ))}
        </div>
      )}

      {/* Model drift chart */}
      {data?.metrics_history && data.metrics_history.length > 1 && (
        <div className="card p-4 mb-5">
          <p className="section-title">Model Drift — Fraud F1 &amp; ROC-AUC over retrains</p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={data.metrics_history} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="timestamp" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5,10)} />
              <YAxis tick={{ fontSize: 10 }} domain={[0, 1]} />
              <Tooltip contentStyle={{ fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="fraud_f1" name="Fraud F1" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="roc_auc" name="ROC-AUC" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Datasets */}
      <div className="mb-5">
        <h3 className="section-title text-base mb-3">Datasets Used</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {DATASETS.map(d => (
            <div key={d.name} className="card p-4 flex gap-3">
              <div className={`w-8 h-8 rounded-lg shrink-0 flex items-center justify-center bg-${d.color}-100 dark:bg-${d.color}-900/30`}>
                <d.icon className={`w-4 h-4 text-${d.color}-600 dark:text-${d.color}-400`} />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{d.name}</p>
                <p className="text-xs text-blue-600 dark:text-blue-400 font-medium mt-0.5">Used for: {d.feature}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">{d.how}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* FinRAG vs ChatGPT */}
      <div className="card p-5 mb-5">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4 text-blue-600" />
          Why FinRAG Copilot vs ChatGPT / Claude / Gemini?
        </h3>
        <div className="overflow-x-auto">
          <table className="data-table min-w-[600px] text-xs">
            <thead>
              <tr>
                <th>Feature</th>
                <th>FinRAG Copilot</th>
                <th>ChatGPT / Claude / Gemini</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Source of answers", "Your own uploaded documents (10-K, annual report)", "Training data up to a cutoff — may be outdated or hallucinated"],
                ["Citation accuracy", "Every number cited to exact page, section and table", "No citation; cannot verify which page a number came from"],
                ["Indian filings", "Handles ₹ crore / lakh, FY2023-24, Ind AS, BSE/NSE reports", "Limited or no Indian GAAP / Ind AS understanding"],
                ["Numeric grounding", "Verifies every number in the answer against the source text", "No verification — confidently incorrect numbers are common"],
                ["Your data privacy", "Documents stay in your account's local storage only", "Uploaded files go to OpenAI/Anthropic/Google servers permanently"],
                ["Offline / air-gapped", "Runs on your own server with python app.py", "Requires internet and a cloud account"],
                ["RAG architecture", "Metadata-driven hybrid BM25 + dense, multi-hop, HyDE", "Black-box retrieval with no transparency"],
                ["Confidence score", "Shows confidence + figures-verified count per answer", "No per-answer reliability signal"],
              ].map(([f, us, them]) => (
                <tr key={f}>
                  <td className="font-medium">{f}</td>
                  <td className="text-emerald-700 dark:text-emerald-400">{us}</td>
                  <td className="text-slate-500">{them}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Security */}
      <div className="card p-5">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-blue-600" />
          How we protect your statements and transactions
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[
            { title: "Documents never leave your server", body: "Uploaded PDFs/HTML are stored in your account's private folder on the server. They are not sent to any third-party service except as text chunks to the Gemini embedding API." },
            { title: "Short-lived signed links", body: "Original document links are signed with a JWT valid for 5 minutes only. The key is derived separately from the sign-in key — a stolen login token cannot open documents." },
            { title: "Content Security Policy", body: "Original HTML documents are served inside a CSP sandbox (no scripts, no cross-origin requests) so a malicious filing cannot attack the viewer's browser." },
            { title: "Transaction data isolation", body: "All API endpoints are scoped to the signed-in user's ID. No query returns another user's transactions, documents or conversations." },
            { title: "OTP-gated account actions", body: "Deleting your account and resetting your password both require an email OTP. This prevents a stolen session from permanently destroying your data." },
            { title: "No PII sent to AI models", body: "Only the text of financial documents and transaction descriptions are sent to Gemini. Names, account numbers and email addresses are never included in AI prompts." },
          ].map(s => (
            <div key={s.title} className="flex gap-2.5 p-3 rounded-lg bg-slate-50 dark:bg-[#1a2740]">
              <Shield className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{s.title}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppLayout>
  );
}
