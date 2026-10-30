"use client";
import { useEffect, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { TrendingUp, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface CreditData {
  score: number;
  base: number;
  factors: Array<{ name: string; impact: string; detail: string; score_contribution: number }>;
  rating: string;
}

function ScoreArc({ score }: { score: number }) {
  const pct = (score - 300) / 550;
  const color = score >= 750 ? "#10b981" : score >= 650 ? "#f59e0b" : score >= 550 ? "#f97316" : "#ef4444";
  const label = score >= 750 ? "Excellent" : score >= 700 ? "Good" : score >= 650 ? "Fair" : score >= 550 ? "Poor" : "Very Poor";
  return (
    <div className="flex flex-col items-center py-6">
      <div className="relative w-40 h-20 overflow-hidden">
        <div className="w-40 h-40 rounded-full border-[14px] border-slate-200 dark:border-[#1e3352] absolute top-0" />
        <div className="w-40 h-40 rounded-full border-[14px] absolute top-0 transition-all duration-700"
          style={{
            borderColor: "transparent",
            borderTopColor: color,
            borderRightColor: color,
            transform: `rotate(${-180 + pct * 180}deg)`,
            transformOrigin: "center",
          }} />
        <div className="absolute inset-x-0 bottom-0 flex flex-col items-center">
          <span className="text-3xl font-bold tabular-nums" style={{ color }}>{score}</span>
          <span className="text-xs text-slate-500 mt-0.5">{label}</span>
        </div>
      </div>
      <p className="text-xs text-slate-400 mt-2">Range: 300 – 850</p>
    </div>
  );
}

export default function CreditScorePage() {
  const [data, setData] = useState<CreditData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<CreditData>("/api/credit-score").then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <AppLayout>
      <div className="page-header">
        <h2 className="page-title">Credit Score</h2>
        <p className="page-desc">Estimated score based on your real account behaviour — not a bureau score</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card col-span-1">
          {loading ? <div className="skeleton h-48 rounded-xl" /> : data ? (
            <ScoreArc score={data.score} />
          ) : <p className="text-center text-xs text-slate-400 py-12">No data</p>}
        </div>

        <div className="card col-span-1 md:col-span-2 p-4">
          <h3 className="section-title">Score Factors</h3>
          {loading ? (
            <div className="space-y-3">{[...Array(5)].map((_,i) => <div key={i} className="skeleton h-14 rounded-lg" />)}</div>
          ) : data?.factors ? (
            <div className="space-y-3">
              {data.factors.map(f => (
                <div key={f.name} className="p-3 rounded-lg bg-slate-50 dark:bg-[#1a2740] flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{f.name}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-snug">{f.detail}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <span className={cn("badge", f.impact === "positive" ? "badge-green" : f.impact === "negative" ? "badge-red" : "badge-yellow")}>
                      {f.impact}
                    </span>
                    <p className={cn("text-xs font-bold mt-1 tabular-nums",
                      f.score_contribution >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                    )}>
                      {f.score_contribution >= 0 ? "+" : ""}{f.score_contribution} pts
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400 text-center py-8">Import transactions to see your credit score factors.</p>
          )}
        </div>
      </div>

      <div className="card p-4 mt-4">
        <div className="flex items-start gap-2">
          <Info className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">About this score</p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
              This is an <strong>estimated</strong> credit score (300–850) computed from your imported transaction data —
              payment regularity, debt load, account age, fraud history and budget adherence. It is <strong>not</strong> a
              bureau-verified CIBIL/Experian score and should not be used for lending decisions. The factors shown
              explain exactly which data points are driving the number up or down.
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
