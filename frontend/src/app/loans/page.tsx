"use client";
import { useState, useEffect } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
type Fmt = (v: unknown) => [string, string];

interface AmortRow { year: number; principal: number; interest: number; balance: number; }

export default function LoansPage() {
  const [principal, setPrincipal] = useState(2000000);
  const [rate, setRate] = useState(8.5);
  const [tenure, setTenure] = useState(20);
  const [extra, setExtra] = useState(0);
  const [rows, setRows] = useState<AmortRow[]>([]);
  const [emi, setEmi] = useState<number | null>(null);
  const [totalInterest, setTotalInterest] = useState<number | null>(null);
  const [savings, setSavings] = useState<{ interest_saved: number; months_saved: number } | null>(null);

  useEffect(() => {
    apiFetch<{ schedule: AmortRow[]; emi: number; total_interest: number; prepayment_savings?: typeof savings }>(
      `/api/loan/amortization?principal=${principal}&annual_rate=${rate}&tenure_months=${tenure*12}&extra_monthly=${extra}`
    ).then(d => {
      setRows(d.schedule ?? []); setEmi(d.emi); setTotalInterest(d.total_interest);
      setSavings(d.prepayment_savings ?? null);
    }).catch(() => {});
  }, [principal, rate, tenure, extra]);

  return (
    <AppLayout>
      <div className="page-header"><h2 className="page-title">Loans &amp; EMI</h2><p className="page-desc">EMI calculator with amortization schedule and prepayment analysis</p></div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        {[
          { label: "Loan amount (₹)", value: principal, set: setPrincipal, min: 10000, max: 100000000, step: 10000 },
          { label: "Annual rate (%)", value: rate, set: setRate, min: 1, max: 30, step: 0.1 },
          { label: "Tenure (years)", value: tenure, set: setTenure, min: 1, max: 30, step: 1 },
        ].map(f => (
          <div key={f.label} className="card p-4">
            <label className="label">{f.label}</label>
            <input type="range" min={f.min} max={f.max} step={f.step} value={f.value}
              onChange={e => f.set(Number(e.target.value))}
              className="w-full accent-blue-600 mb-1" />
            <p className="text-sm font-semibold text-blue-700 dark:text-blue-300 text-center">
              {f.label.includes("₹") ? formatMoney(f.value) : f.value}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
        {emi !== null && (
          <div className="stat-card"><span className="stat-label">Monthly EMI</span><span className="stat-value text-blue-700 dark:text-blue-300">{formatMoney(emi)}</span></div>
        )}
        {totalInterest !== null && (
          <div className="stat-card"><span className="stat-label">Total Interest</span><span className="stat-value text-amber-600">{formatMoney(totalInterest)}</span></div>
        )}
        <div className="card p-4">
          <label className="label">Extra monthly payment (₹)</label>
          <input type="number" className="input" min={0} value={extra} onChange={e => setExtra(Number(e.target.value))} placeholder="0" />
          {savings && (
            <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-2">
              Save {formatMoney(savings.interest_saved)} interest · close {savings.months_saved} months early
            </p>
          )}
        </div>
      </div>

      {rows.length > 0 && (
        <div className="card p-4">
          <p className="section-title">Year-by-Year Breakdown</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={rows} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="year" tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `₹${(v/100000).toFixed(0)}L`} />
              <Tooltip formatter={((v: unknown) => [formatMoney(Number(v)), ""]) as Fmt} contentStyle={{ fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="principal" name="Principal" stackId="a" fill="#2563eb" />
              <Bar dataKey="interest" name="Interest" stackId="a" fill="#93c5fd" radius={[3,3,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </AppLayout>
  );
}
