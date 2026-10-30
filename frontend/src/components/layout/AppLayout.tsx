"use client";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard":    "Dashboard",
  "/transactions": "Transactions",
  "/upload":       "Upload Statement",
  "/fraud-alerts": "Fraud Alerts",
  "/predictive":   "Predictive Modeling",
  "/insights":     "Insights",
  "/investments":  "Investments",
  "/loans":        "Loans & EMI",
  "/credit-score": "Credit Score",
  "/rag":          "FinRAG Copilot",
  "/profile":      "Profile",
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[--bg]">
        <div className="w-8 h-8 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
      </div>
    );
  }
  if (!user) return null;

  const title = PAGE_TITLES[pathname] ?? "FinRAG AI";

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)]">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar title={title} />
        <main className="flex-1 overflow-y-auto p-5">
          {children}
        </main>
      </div>
    </div>
  );
}
