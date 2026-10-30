"use client";
import { useEffect, useState } from "react";
import AppLayout from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Loader2, Trash2, ShieldCheck, ShieldAlert } from "lucide-react";

interface ProfileData {
  name: string; email: string; currency: string; budget_limit: number;
  security_status: string; trust_score: number; account_created: string;
}

export default function ProfilePage() {
  const { user, refresh, logout } = useAuth();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [name, setName] = useState(""); const [currency, setCurrency] = useState("INR"); const [budget, setBudget] = useState("");
  const [oldPwd, setOldPwd] = useState(""); const [newPwd, setNewPwd] = useState(""); const [confirmPwd, setConfirmPwd] = useState("");
  const [deleteOtp, setDeleteOtp] = useState(""); const [deleteStep, setDeleteStep] = useState<"idle"|"sent"|"confirming">("idle");
  const [msg, setMsg] = useState(""); const [err, setErr] = useState(""); const [loading, setLoading] = useState(false);

  const flash = (m: string, isErr = false) => { if (isErr) setErr(m); else setMsg(m); setTimeout(() => { setErr(""); setMsg(""); }, 4000); };

  useEffect(() => {
    apiFetch<{ profile: ProfileData }>("/api/profile").then(d => {
      setProfile(d.profile);
      setName(d.profile.name); setCurrency(d.profile.currency ?? "INR"); setBudget(String(d.profile.budget_limit ?? ""));
    }).catch(() => {});
  }, []);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault(); setLoading(true);
    try {
      await apiFetch("/api/profile", { method: "PUT", body: JSON.stringify({ name, currency, budget_limit: Number(budget) || null }) });
      await refresh(); flash("Profile saved.");
    } catch (ex: unknown) { flash(ex instanceof Error ? ex.message : "Failed", true); }
    finally { setLoading(false); }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPwd !== confirmPwd) { flash("Passwords do not match", true); return; }
    if (newPwd.length < 12) { flash("Minimum 12 characters", true); return; }
    setLoading(true);
    try {
      await apiFetch("/api/profile/password", { method: "POST", body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }) });
      setOldPwd(""); setNewPwd(""); setConfirmPwd(""); flash("Password changed.");
    } catch (ex: unknown) { flash(ex instanceof Error ? ex.message : "Failed", true); }
    finally { setLoading(false); }
  }

  async function requestDeleteOtp() {
    setLoading(true);
    try {
      await apiFetch("/api/auth/delete-account-otp", { method: "POST" });
      setDeleteStep("sent"); flash("OTP sent to your email.");
    } catch (ex: unknown) { flash(ex instanceof Error ? ex.message : "Failed", true); }
    finally { setLoading(false); }
  }

  async function confirmDelete(e: React.FormEvent) {
    e.preventDefault(); setLoading(true);
    try {
      await apiFetch("/api/auth/delete-account", { method: "DELETE", body: JSON.stringify({ otp: deleteOtp }) });
      logout();
    } catch (ex: unknown) { flash(ex instanceof Error ? ex.message : "Failed", true); }
    finally { setLoading(false); }
  }

  return (
    <AppLayout>
      <div className="page-header"><h2 className="page-title">Profile</h2><p className="page-desc">Manage your account settings</p></div>

      {msg && <p className="mb-4 text-xs text-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-400 px-3 py-2 rounded-lg">{msg}</p>}
      {err && <p className="mb-4 text-xs text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400 px-3 py-2 rounded-lg">{err}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Profile info */}
        <div className="card p-4">
          <h3 className="section-title">Account Details</h3>
          {profile && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-[#1a2740] mb-4">
              {profile.security_status === "Strong"
                ? <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
                : <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0" />}
              <div>
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">Security: {profile.security_status}</p>
                <p className="text-xs text-slate-500">Trust score: {profile.trust_score}/100</p>
              </div>
            </div>
          )}
          <form onSubmit={saveProfile} className="space-y-3">
            <div><label className="label">Full name</label><input className="input" value={name} onChange={e => setName(e.target.value)} /></div>
            <div><label className="label">Email</label><input className="input" value={user?.email ?? ""} disabled /></div>
            <div>
              <label className="label">Default currency</label>
              <select className="input" value={currency} onChange={e => setCurrency(e.target.value)}>
                {["INR","USD","EUR","GBP","SGD","AED"].map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div><label className="label">Monthly budget limit (optional)</label><input type="number" className="input" value={budget} onChange={e => setBudget(e.target.value)} placeholder="e.g. 90000" /></div>
            <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save changes"}</button>
          </form>
        </div>

        {/* Change password */}
        <div className="card p-4">
          <h3 className="section-title">Change Password</h3>
          <form onSubmit={changePassword} className="space-y-3">
            <div><label className="label">Current password</label><input type="password" className="input" value={oldPwd} onChange={e => setOldPwd(e.target.value)} /></div>
            <div><label className="label">New password (min 12 chars)</label><input type="password" className="input" value={newPwd} onChange={e => setNewPwd(e.target.value)} /></div>
            <div><label className="label">Confirm new password</label><input type="password" className="input" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} /></div>
            <button type="submit" disabled={loading || !oldPwd || !newPwd} className="btn-primary w-full">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Change password"}</button>
          </form>
        </div>

        {/* Delete account */}
        <div className="card p-4 border-red-200 dark:border-red-900/50 md:col-span-2">
          <h3 className="text-sm font-semibold text-red-600 dark:text-red-400 mb-1 flex items-center gap-2"><Trash2 className="w-4 h-4" /> Delete Account</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">This permanently deletes all your transactions, documents, alerts and conversations. This action cannot be undone.</p>
          {deleteStep === "idle" && (
            <button onClick={requestDeleteOtp} disabled={loading} className="btn-danger">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Delete my account"}
            </button>
          )}
          {deleteStep === "sent" && (
            <form onSubmit={confirmDelete} className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="label">Enter the 6-digit OTP sent to your email</label>
                <input type="text" maxLength={6} className="input tracking-widest text-center text-lg" value={deleteOtp} onChange={e => setDeleteOtp(e.target.value)} placeholder="000000" />
              </div>
              <button type="submit" disabled={loading || deleteOtp.length < 6} className="btn-danger">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Confirm delete"}
              </button>
              <button type="button" onClick={() => setDeleteStep("idle")} className="btn-ghost">Cancel</button>
            </form>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
