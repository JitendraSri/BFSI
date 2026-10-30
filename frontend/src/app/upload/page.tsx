"use client";
import { useRef, useState, useEffect } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { Upload, FileText, CheckCircle, XCircle, RotateCcw, Loader2 } from "lucide-react";
import { formatMoney, formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface ImportRecord { batch_id: string; file_name: string; imported_at: string; count: number; rolled_back_at?: string; }
interface Preview { rows: Array<{ description: string; amount: number; direction: string; timestamp: string }>; rejected: number; duplicates: number; batch_id?: string; }

export default function UploadPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [imports, setImports] = useState<ImportRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");

  const flash = (m: string, isErr = false) => { isErr ? setErr(m) : setMsg(m); setTimeout(() => { setErr(""); setMsg(""); }, 5000); };

  useEffect(() => { loadImports(); }, []);
  function loadImports() {
    apiFetch<{ imports: ImportRecord[] }>("/api/imports").then(d => setImports(d.imports ?? [])).catch(() => {});
  }

  async function handleFile(file: File) {
    if (!file) return;
    setLoading(true); setPreview(null); setErr("");
    const form = new FormData(); form.append("file", file);
    try {
      const d = await apiFetch<Preview>("/api/upload/preview", { method: "POST", headers: {}, body: form });
      setPreview(d);
    } catch (ex: unknown) { flash(ex instanceof Error ? ex.message : "Upload failed", true); }
    finally { setLoading(false); }
  }

  async function confirmImport() {
    if (!preview?.batch_id) return;
    setConfirming(true);
    try {
      await apiFetch("/api/upload/confirm", { method: "POST", body: JSON.stringify({ batch_id: preview.batch_id }) });
      setPreview(null); flash(`Imported ${preview.rows.length} transactions.`); loadImports();
    } catch (ex: unknown) { flash(ex instanceof Error ? ex.message : "Confirm failed", true); }
    finally { setConfirming(false); }
  }

  async function rollback(batch_id: string) {
    await apiFetch(`/api/imports/${batch_id}/rollback`, { method: "POST" }).catch(() => {});
    flash("Import rolled back."); loadImports();
  }

  return (
    <AppLayout>
      <div className="page-header"><h2 className="page-title">Upload Statement</h2><p className="page-desc">Import CSV, Excel, PDF or image bank statements</p></div>

      {msg && <p className="mb-4 text-xs text-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-400 px-3 py-2 rounded-lg">{msg}</p>}
      {err && <p className="mb-4 text-xs text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400 px-3 py-2 rounded-lg">{err}</p>}

      {/* Drop zone */}
      <div
        className="card p-8 text-center cursor-pointer hover:border-blue-400 dark:hover:border-blue-600 border-2 border-dashed border-slate-300 dark:border-[#1e3352] transition-colors mb-5"
        onClick={() => fileRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
      >
        <input ref={fileRef} type="file" className="hidden" accept=".csv,.xlsx,.xls,.pdf,.jpg,.jpeg,.png,.webp"
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
        {loading ? <Loader2 className="w-8 h-8 text-blue-600 mx-auto animate-spin" /> : <Upload className="w-8 h-8 text-slate-400 mx-auto mb-2" />}
        <p className="text-sm font-medium text-slate-600 dark:text-slate-300 mt-2">Click or drag a file here</p>
        <p className="text-xs text-slate-400 mt-1">CSV · Excel · PDF · Image (JPEG, PNG, WebP)</p>
        <p className="text-xs text-slate-400 mt-2">Supports Indian bank formats: HDFC, SBI, ICICI, Axis, Kotak</p>
      </div>

      {/* Preview */}
      {preview && (
        <div className="card overflow-hidden mb-5">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-[#1e3352] flex items-center justify-between">
            <div>
              <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{preview.rows.length} transactions ready to import</span>
              {preview.rejected > 0 && <span className="ml-2 badge badge-red">{preview.rejected} rejected</span>}
              {preview.duplicates > 0 && <span className="ml-2 badge badge-yellow">{preview.duplicates} duplicates skipped</span>}
            </div>
            <div className="flex gap-2">
              <button onClick={() => setPreview(null)} className="btn-ghost text-xs">Discard</button>
              <button onClick={confirmImport} disabled={confirming} className="btn-primary text-xs">
                {confirming ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />} Confirm import
              </button>
            </div>
          </div>
          <div className="overflow-x-auto max-h-64">
            <table className="data-table min-w-[500px]">
              <thead><tr><th>Date</th><th>Description</th><th className="text-right">Amount</th><th>Direction</th></tr></thead>
              <tbody>
                {preview.rows.slice(0, 30).map((r, i) => (
                  <tr key={i}>
                    <td className="text-xs">{formatDate(r.timestamp)}</td>
                    <td className="max-w-48 truncate text-xs">{r.description}</td>
                    <td className="text-right text-xs tabular-nums">{formatMoney(r.amount)}</td>
                    <td><span className={cn("badge text-xs", r.direction === "credit" ? "badge-green" : "badge-slate")}>{r.direction}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Import history */}
      {imports.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-[#1e3352]">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">Import History</span>
          </div>
          <table className="data-table">
            <thead><tr><th>File</th><th>Date</th><th>Records</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {imports.map(imp => (
                <tr key={imp.batch_id}>
                  <td className="flex items-center gap-1.5 text-xs"><FileText className="w-3.5 h-3.5 text-slate-400" />{imp.file_name}</td>
                  <td className="text-xs">{formatDate(imp.imported_at)}</td>
                  <td className="text-xs">{imp.count}</td>
                  <td>{imp.rolled_back_at ? <span className="badge badge-slate">Rolled back</span> : <span className="badge badge-green">Active</span>}</td>
                  <td>
                    {!imp.rolled_back_at && (
                      <button onClick={() => rollback(imp.batch_id)} className="btn-ghost py-1 px-2 text-xs text-amber-600 hover:text-amber-700">
                        <RotateCcw className="w-3 h-3" /> Undo
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}
