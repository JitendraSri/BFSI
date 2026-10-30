"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/lib/api";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export default function LoginPage() {
  const [tab, setTab] = useState<"login" | "forgot">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [step, setStep] = useState<"email" | "otp">("email");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const { login } = useAuth();
  const router = useRouter();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally { setLoading(false); }
  }

  async function handleForgotSend(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await apiFetch("/api/auth/forgot-password", {
        method: "POST", body: JSON.stringify({ email }),
      });
      setStep("otp");
      setInfo("OTP sent to your email.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally { setLoading(false); }
  }

  async function handleForgotReset(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await apiFetch("/api/auth/reset-password", {
        method: "POST", body: JSON.stringify({ email, otp, new_password: newPwd }),
      });
      setInfo("Password reset! Please log in.");
      setTab("login"); setStep("email");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally { setLoading(false); }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#0b1120] px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-lg mb-3">F</div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">FinRAG AI</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">BFSI Intelligence Platform</p>
        </div>

        <div className="card p-6">
          {/* Tabs */}
          <div className="flex border-b border-slate-200 dark:border-[#1e3352] mb-5 -mx-6 px-6">
            <button
              className={`pb-2.5 mr-4 text-sm font-medium border-b-2 transition-colors ${tab === "login" ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"}`}
              onClick={() => { setTab("login"); setError(""); setInfo(""); }}
            >Sign in</button>
            <button
              className={`pb-2.5 text-sm font-medium border-b-2 transition-colors ${tab === "forgot" ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"}`}
              onClick={() => { setTab("forgot"); setError(""); setInfo(""); setStep("email"); }}
            >Reset password</button>
          </div>

          {error && <p className="mb-3 text-xs text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400 px-3 py-2 rounded-lg">{error}</p>}
          {info  && <p className="mb-3 text-xs text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-400 px-3 py-2 rounded-lg">{info}</p>}

          {tab === "login" && (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="label">Email address</label>
                <input type="email" required className="input" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
              </div>
              <div>
                <label className="label">Password</label>
                <div className="relative">
                  <input type={showPwd ? "text" : "password"} required className="input pr-9" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
                  <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Sign in"}
              </button>
            </form>
          )}

          {tab === "forgot" && step === "email" && (
            <form onSubmit={handleForgotSend} className="space-y-4">
              <div>
                <label className="label">Email address</label>
                <input type="email" required className="input" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send OTP"}
              </button>
            </form>
          )}

          {tab === "forgot" && step === "otp" && (
            <form onSubmit={handleForgotReset} className="space-y-4">
              <div>
                <label className="label">OTP (6-digit code from email)</label>
                <input type="text" required maxLength={6} className="input tracking-widest text-center text-lg" value={otp} onChange={e => setOtp(e.target.value)} placeholder="000000" />
              </div>
              <div>
                <label className="label">New password (min 12 chars)</label>
                <input type="password" required minLength={12} className="input" value={newPwd} onChange={e => setNewPwd(e.target.value)} placeholder="••••••••••••" />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Reset password"}
              </button>
              <button type="button" onClick={() => setStep("email")} className="btn-ghost w-full text-slate-500">← Back</button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-slate-500 dark:text-slate-400 mt-4">
          No account?{" "}
          <Link href="/register" className="text-blue-600 hover:underline font-medium">Create one</Link>
        </p>
      </div>
    </div>
  );
}
