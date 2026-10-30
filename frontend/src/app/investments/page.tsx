"use client";
import { useEffect, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import { Plus, RefreshCw, Loader2 } from "lucide-react";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend } from "recharts";
type Fmt = (v: unknown, n?: unknown) => [string, string];
import { cn } from "@/lib/utils";

interface Investment { _id: string; name: string; asset_type: string; quantity: number; purchase_price: number; current_price: number; currency: string; }

const TYPE_COLORS: Record<string, string> = {
  stock: "#2563eb", mutual_fund: "#0ea5e9", gold: "#f59e0b",
  fd: "#10b981", crypto: "#6366f1", real_estate: "#8b5cf6", other: "#94a3b8",
};
const TYPES = ["stock","mutual_fund","gold","fd","crypto","real_estate","other"];

export default function InvestmentsPage() {
  const [items, setItems] = useState<Investment[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", asset_type: "stock", quantity: 1, purchase_price: 0, current_price: 0, currency: "INR" });
  const [saving, setSaving] = useState(false);
  const [revalId, setRevalId] = useState<string | null>(null);
  const [newPrice, setNewPrice] = useState<Record<string, string>>({});

  const load = () => {
    setLoading(true);
    apiFetch<{ investments: Investment[] }>("/api/investments").then(d => setItems(d.investments ?? [])).finally(() => setLoading(false));
  };
  useEffect(load, []);

  async function addInvestment(e: React.FormEvent) {
    e.preventDefault(); setSaving(true);
    await apiFetch("/api/investments", { method: "POST", body: JSON.stringify(form) }).catch(() => {});
    setSaving(false); setShowForm(false); setForm({ name: "", asset_type: "stock", quantity: 1, purchase_price: 0, current_price: 0, currency: "INR" }); load();
  }

  async function revalue(id: string) {
    const price = parseFloat(newPrice[id]);
    if (!price || isNaN(price)) return;
    await apiFetch(`/api/investments/${id}`, { method: "PATCH", body: JSON.stringify({ current_price: price }) }).catch(() => {});
    setRevalId(null); setNewPrice(n => ({ ...n, [id]: "" })); load();
  }

  const totalValue = items.reduce((s, i) => s + i.current_price * i.quantity, 0);
  const totalCost  = items.reduce((s, i) => s + i.purchase_price * i.quantity, 0);
  const totalReturn = totalValue - totalCost;
  const returnPct = totalCost > 0 ? (totalReturn / totalCost) * 100 : 0;

  const pieData = TYPES.map(t => ({
    name: t.replace("_", " "),
    value: items.filter(i => i.asset_type === t).reduce((s, i) => s + i.current_price * i.quantity, 0),
  })).filter(d => d.value > 0);

  return (
    <AppLayout>
      <div className="page-header flex items-center justify-between">
        <div><h2 className="page-title">Investments</h2><p className="page-desc">Track your portfolio performance</p></div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary"><Plus className="w-4 h-4" /> Add holding</button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="stat-card"><span className="stat-label">Portfolio Value</span><span className="stat-value text-blue-700 dark:text-blue-300">{formatMoney(totalValue)}</span></div>
        <div className="stat-card"><span className="stat-label">Total Cost</span><span className="stat-value">{formatMoney(totalCost)}</span></div>
        <div className="stat-card"><span className="stat-label">Return</span>
          <span className={cn("stat-value", returnPct >= 0 ? "text-emerald-600" : "text-red-600")}>
            {returnPct >= 0 ? "+" : ""}{returnPct.toFixed(1)}% ({formatMoney(totalReturn)})
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        {/* Allocation */}
        <div className="card p-4">
          <p className="section-title">Allocation</p>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart><Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={65} label={({ name, percent }) => `${name} ${((percent ?? 0)*100).toFixed(0)}%`} labelLine={false}>
                {pieData.map((_, i) => <Cell key={i} fill={Object.values(TYPE_COLORS)[i % Object.keys(TYPE_COLORS).length]} />)}
              </Pie><Tooltip formatter={((v: unknown) => [formatMoney(Number(v)), "Value"]) as Fmt} contentStyle={{ fontSize: 11 }} /></PieChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-slate-400 text-center py-12">No holdings yet.</p>}
        </div>

        {/* Holdings table */}
        <div className="card col-span-1 md:col-span-2 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table min-w-[500px]">
              <thead><tr><th>Name</th><th>Type</th><th className="text-right">Qty</th><th className="text-right">Cost</th><th className="text-right">Value</th><th className="text-right">Return</th><th></th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={7}><div className="skeleton h-8 rounded" /></td></tr>
                  : items.length === 0 ? <tr><td colSpan={7} className="text-center text-slate-400 py-8 text-sm">No holdings. Add one above.</td></tr>
                  : items.map(inv => {
                    const val = inv.current_price * inv.quantity;
                    const cost = inv.purchase_price * inv.quantity;
                    const ret = val - cost;
                    const retPct = cost > 0 ? (ret / cost) * 100 : 0;
                    return (
                      <tr key={inv._id}>
                        <td className="font-medium text-xs">{inv.name}</td>
                        <td><span className="badge badge-blue text-xs">{inv.asset_type.replace("_"," ")}</span></td>
                        <td className="text-right text-xs tabular-nums">{inv.quantity}</td>
                        <td className="text-right text-xs tabular-nums">{formatMoney(cost, inv.currency)}</td>
                        <td className="text-right text-xs tabular-nums font-medium">{formatMoney(val, inv.currency)}</td>
                        <td className={cn("text-right text-xs tabular-nums font-medium", ret >= 0 ? "text-emerald-600" : "text-red-600")}>
                          {ret >= 0 ? "+" : ""}{retPct.toFixed(1)}%
                        </td>
                        <td>
                          {revalId === inv._id ? (
                            <div className="flex gap-1">
                              <input type="number" className="input py-1 text-xs w-20" value={newPrice[inv._id] ?? ""} onChange={e => setNewPrice(n => ({ ...n, [inv._id]: e.target.value }))} placeholder="New price" />
                              <button onClick={() => revalue(inv._id)} className="btn-primary py-1 px-2 text-xs">✓</button>
                              <button onClick={() => setRevalId(null)} className="btn-ghost py-1 px-2 text-xs">✗</button>
                            </div>
                          ) : (
                            <button onClick={() => setRevalId(inv._id)} className="btn-ghost py-1 px-2 text-xs"><RefreshCw className="w-3 h-3" /></button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="card p-4">
          <h3 className="section-title">Add Holding</h3>
          <form onSubmit={addInvestment} className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div><label className="label">Name</label><input className="input" value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} placeholder="HDFC Bank" /></div>
            <div><label className="label">Type</label><select className="input" value={form.asset_type} onChange={e => setForm(f=>({...f,asset_type:e.target.value}))}>
              {TYPES.map(t => <option key={t} value={t}>{t.replace("_"," ")}</option>)}
            </select></div>
            <div><label className="label">Quantity</label><input type="number" className="input" min={0} value={form.quantity} onChange={e => setForm(f=>({...f,quantity:Number(e.target.value)}))} /></div>
            <div><label className="label">Purchase price (₹)</label><input type="number" className="input" min={0} value={form.purchase_price} onChange={e => setForm(f=>({...f,purchase_price:Number(e.target.value)}))} /></div>
            <div><label className="label">Current price (₹)</label><input type="number" className="input" min={0} value={form.current_price} onChange={e => setForm(f=>({...f,current_price:Number(e.target.value)}))} /></div>
            <div className="flex items-end">
              <button type="submit" disabled={saving} className="btn-primary w-full">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Add"}</button>
            </div>
          </form>
        </div>
      )}
    </AppLayout>
  );
}
