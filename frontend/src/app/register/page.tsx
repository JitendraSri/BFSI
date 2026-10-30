"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Loader2 } from "lucide-react";

export default function RegisterPage() {
  const [step, setStep] = useState<"form" | "otp">("form");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await apiFetch("/api/register", {
        method: "POST", body: JSON.stringify({ name, email, password }),
      });
      setStep("otp");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally { setLoading(false); }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await apiFetch("/api/verify-email", {
        method: "POST", body: JSON.stringify({ email, otp }),
      });
      router.replace("/login");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally { setLoading(false); }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#0b1120] px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-lg mb-3">F</div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Create account</h1>
          <p className="text-xs text-slate-500 mt-0.5">Join FinRAG AI</p>
        </div>

        <div className="card p-6">
          {error && <p className="mb-3 text-xs text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400 px-3 py-2 rounded-lg">{error}</p>}

          {step === "form" && (
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="label">Full name</label>
                <input type="text" required className="input" value={name} onChange={e => setName(e.target.value)} placeholder="Rahul Sharma" />
              </div>
              <div>
                <label className="label">Email address</label>
                <input type="email" required className="input" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
              </div>
              <div>
                <label className="label">Password (min 12 chars)</label>
                <input type="password" required minLength={12} className="input" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••••••" />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create account"}
              </button>
            </form>
          )}

          {step === "otp" && (
            <form onSubmit={handleVerify} className="space-y-4">
              <p className="text-xs text-slate-600 dark:text-slate-400 bg-blue-50 dark:bg-blue-900/20 px-3 py-2 rounded-lg">
                We sent a 6-digit code to <strong>{email}</strong>. Enter it below to verify your account.
              </p>
              <div>
                <label className="label">Verification code</label>
                <input type="text" required maxLength={6} className="input tracking-widest text-center text-lg" value={otp} onChange={e => setOtp(e.target.value)} placeholder="000000" />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify email"}
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-slate-500 dark:text-slate-400 mt-4">
          Already have an account?{" "}
          <Link href="/login" className="text-blue-600 hover:underline font-medium">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
