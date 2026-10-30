"use client";
import { useEffect, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { formatMoney, formatDate, riskColor } from "@/lib/utils";
import {
  TrendingUp, TrendingDown, ShieldCheck, ShieldAlert,
  RefreshCw, ArrowUpRight, Repeat, Zap, AlertTriangle,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend,
} from "recharts";
type Fmt = (v: unknown, n?: unknown) => [string, string];

interface DashData {
  user_stats: {
    total_balance: number;
    total_transactions: number;
    suspicious_activity: number;
    disputed_transactions: number;
    trust_score: number;
    security_status: string;
    fraud_risk_level: string;
  };
  monthly_volume?: Array<{ date: string; value: number }>;
  income_expense_data?: Array<{ date: string; income: number; expense: number }>;
  category_data?: Array<{ category: string; amount: number }>;
  prediction_data?: Array<{ date: string; actual?: number; predicted?: number }>;
  subscriptions?: Array<{ description: string; amount: number; interval: string }>;
  monthly_subscription_total?: number;
  spend_insight?: { category: string; amount: number; previous_amount: number; change: number } | null;
  forecast_history?: { months_with_spending: number; first_month: string; last_month: string };
  recent_alerts?: Array<{ id: string; description: string; risk_score: number; risk_level: string; timestamp: string }>;
  fraud_trend_data?: Array<{ date: string; count: number }>;
  currency_selected?: string;
  previous_login_at?: string;
  untagged_currency_assumed?: boolean;
}

const CAT_COLORS = ["#2563eb", "#0ea5e9", "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444"];

export default function DashboardPage() {
  const [data, setData] = useState<DashData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<DashData>("/api/dashboard")
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <AppLayout><div className="space-y-4">{[...Array(4)].map((_,i) => <div key={i} className="skeleton h-24 rounded-xl" />)}</div></AppLayout>;
  if (error || !data) return <AppLayout><p className="text-red-500 text-sm">{error || "Failed to load"}</p></AppLayout>;

  const stats = data.user_stats;
  const cur = data.currency_selected ?? "INR";

  return (
    <AppLayout>
      {data.previous_login_at && (
        <p className="text-xs text-slate-400 dark:text-slate-500 mb-4">
          Last sign-in: {formatDate(data.previous_login_at)}
        </p>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div className="stat-card">
          <span className="stat-label">Balance</span>
          <span className="stat-value text-blue-700 dark:text-blue-300">{formatMoney(stats.total_balance, cur)}</span>
          {data.untagged_currency_assumed && <span className="stat-sub">Assumed {cur}</span>}
        </div>
        <div className="stat-card">
          <span className="stat-label">Transactions</span>
          <span className="stat-value">{stats.total_transactions.toLocaleString()}</span>
          <span className="stat-sub">{stats.suspicious_activity} flagged</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Trust Score</span>
          <span className={`stat-value ${stats.trust_score >= 70 ? "text-emerald-600 dark:text-emerald-400" : stats.trust_score >= 40 ? "text-amber-600" : "text-red-600"}`}>
            {stats.trust_score}/100
          </span>
          <span className="stat-sub">{stats.security_status}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Fraud Risk</span>
          <span className={`stat-value ${stats.fraud_risk_level === "High" ? "text-red-600" : stats.fraud_risk_level === "Medium" ? "text-amber-600" : "text-emerald-600"}`}>
            {stats.fraud_risk_level ?? "Low"}
          </span>
          <span className="stat-sub">{stats.disputed_transactions} disputed</span>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* Transaction volume */}
        <div className="card p-4">
          <p className="section-title">Transaction Volume</p>
          {data.monthly_volume?.length ? (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={data.monthly_volume} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={((v: unknown) => [formatMoney(Number(v), cur), "Volume"]) as Fmt} labelFormatter={l => `Date: ${l}`} contentStyle={{ fontSize: 12 }} />
                <Bar dataKey="value" fill="#2563eb" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-slate-400 text-center py-12">No data. Upload a statement.</p>}
        </div>

        {/* Income vs Expense */}
        <div className="card p-4">
          <p className="section-title">Income vs Expense</p>
          {data.income_expense_data?.length ? (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={data.income_expense_data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={((v: unknown, n: unknown) => [formatMoney(Number(v), cur), String(n ?? "")]) as Fmt} contentStyle={{ fontSize: 12 }} />
                <Bar dataKey="income" name="Income" fill="#10b981" radius={[3,3,0,0]} />
                <Bar dataKey="expense" name="Expense" fill="#ef4444" radius={[3,3,0,0]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-slate-400 text-center py-12">No data — import a statement with Debit/Credit columns.</p>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        {/* Spending categories */}
        <div className="card p-4">
          <p className="section-title">Spending Categories</p>
          {data.category_data?.length ? (
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={data.category_data} dataKey="amount" nameKey="category" cx="50%" cy="50%" outerRadius={60} label={({ name, percent }) => `${name} ${((percent ?? 0)*100).toFixed(0)}%`} labelLine={false}>
                  {data.category_data.map((_, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={((v: unknown) => [formatMoney(Number(v), cur), "Amount"]) as Fmt} contentStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-slate-400 text-center py-12">No categorized debit transactions.</p>}
        </div>

        {/* Spend insight */}
        <div className="card p-4 flex flex-col gap-3">
          <p className="section-title">Intelligent Snapshot</p>
          {data.spend_insight ? (
            <div className="space-y-2">
              <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-50 dark:bg-amber-900/20">
                <TrendingUp className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-medium text-amber-800 dark:text-amber-300">{data.spend_insight.category} up</p>
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    {formatMoney(data.spend_insight.amount, cur)} this month vs {formatMoney(data.spend_insight.previous_amount, cur)} last month
                    ({data.spend_insight.change > 0 ? "+" : ""}{formatMoney(data.spend_insight.change, cur)})
                  </p>
                </div>
              </div>
              {stats.fraud_risk_level !== "Low" && (
                <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red-50 dark:bg-red-900/20">
                  <ShieldAlert className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
                  <p className="text-xs text-red-700 dark:text-red-400">
                    Account fraud risk: <strong>{stats.fraud_risk_level}</strong> — {stats.suspicious_activity} suspicious transaction{stats.suspicious_activity !== 1 ? "s" : ""} flagged.
                  </p>
                </div>
              )}
              {stats.security_status === "Strong" && (
                <div className="flex items-start gap-2 p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-900/20">
                  <ShieldCheck className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  <p className="text-xs text-emerald-700 dark:text-emerald-400">Account security is <strong>Strong</strong>. Email verified, no flagged transactions.</p>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400 text-center py-8">Upload statements to see spending insights.</p>
          )}
        </div>

        {/* Recurring payments */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="section-title mb-0">Recurring Payments</p>
            {data.monthly_subscription_total !== undefined && (
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{formatMoney(data.monthly_subscription_total, cur)}/mo</span>
            )}
          </div>
          {data.subscriptions?.length ? (
            <ul className="space-y-2">
              {data.subscriptions.slice(0, 5).map((s, i) => (
                <li key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Repeat className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                    <span className="text-xs text-slate-700 dark:text-slate-300 truncate max-w-28">{s.description}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-medium text-slate-800 dark:text-slate-200">{formatMoney(s.amount, cur)}</span>
                    <p className="text-xs text-slate-400">{s.interval}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-400 text-center py-8">No recurring payments detected.</p>
          )}
        </div>
      </div>

      {/* Forecast + Recent alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Forecast */}
        <div className="card p-4">
          <p className="section-title">Spending Forecast</p>
          {data.prediction_data?.length ? (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={data.prediction_data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={d => d.slice(0,7)} />
                <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={((v: unknown, n: unknown) => [formatMoney(Number(v), cur), String(n ?? "")]) as Fmt} contentStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="actual" name="Actual" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                <Line type="monotone" dataKey="predicted" name="Predicted" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 4 }} connectNulls={false} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-slate-400 text-center py-12">
              {data.forecast_history?.months_with_spending
                ? "Upload a statement to enable the forecast."
                : "No transactions found. Upload a bank statement."}
            </p>
          )}
        </div>

        {/* Recent fraud alerts */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="section-title mb-0">Recent Fraud Alerts</p>
            <a href="/fraud-alerts" className="text-xs text-blue-600 hover:underline flex items-center gap-1">View all <ArrowUpRight className="w-3 h-3" /></a>
          </div>
          {data.recent_alerts?.length ? (
            <ul className="space-y-2">
              {data.recent_alerts.slice(0, 5).map(a => (
                <li key={a.id} className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-[#1e3352]/50 last:border-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <AlertTriangle className={`w-3.5 h-3.5 shrink-0 ${a.risk_level === "High" ? "text-red-500" : "text-amber-500"}`} />
                    <span className="text-xs text-slate-700 dark:text-slate-300 truncate">{a.description}</span>
                  </div>
                  <div className="flex items-center gap-2 ml-2 shrink-0">
                    <span className={`badge text-xs ${riskColor(a.risk_level)}`}>{a.risk_level}</span>
                    <span className="text-xs text-slate-400 tabular-nums">{a.risk_score}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-400 text-center py-12">No fraud alerts. Import statements to begin analysis.</p>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
