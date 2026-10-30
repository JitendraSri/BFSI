"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Upload, CreditCard, ShieldAlert, TrendingUp,
  Briefcase, Calculator, Brain, MessageSquareText, User,
  ChevronLeft, ChevronRight, LogOut, BarChart3,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const NAV = [
  {
    href: "/dashboard",
    icon: LayoutDashboard,
    label: "Dashboard",
    tip: "Overview of your finances — balance, fraud alerts, spending trends and forecast",
  },
  {
    href: "/transactions",
    icon: CreditCard,
    label: "Transactions",
    tip: "Browse, search and filter your full transaction history with CSV export",
  },
  {
    href: "/upload",
    icon: Upload,
    label: "Upload",
    tip: "Import bank statements (CSV, Excel, PDF or image) — duplicates are detected automatically",
  },
  {
    href: "/fraud-alerts",
    icon: ShieldAlert,
    label: "Fraud Alerts",
    tip: "Review AI-flagged suspicious transactions, mark them Legitimate or Fraud",
  },
  {
    href: "/predictive",
    icon: Brain,
    label: "Predictive",
    tip: "Simulate fraud risk for a hypothetical transaction; retrain the ML models on your data",
  },
  {
    href: "/insights",
    icon: BarChart3,
    label: "Insights",
    tip: "Model metrics, benchmark results, dataset descriptions and FinRAG vs ChatGPT comparison",
  },
  {
    href: "/investments",
    icon: Briefcase,
    label: "Investments",
    tip: "Track your portfolio (stocks, MF, gold, FD, crypto) and get an AI rebalancing review",
  },
  {
    href: "/loans",
    icon: Calculator,
    label: "Loans",
    tip: "EMI calculator, affordability check and full amortization schedule with prepayment modelling",
  },
  {
    href: "/credit-score",
    icon: TrendingUp,
    label: "Credit Score",
    tip: "Your credit score breakdown based on real account behaviour — payment regularity, debt load, account age",
  },
  {
    href: "/rag",
    icon: MessageSquareText,
    label: "FinRAG Copilot",
    tip: "Ask questions about annual reports and 10-K filings — answers are cited to the exact page and table",
  },
  {
    href: "/profile",
    icon: User,
    label: "Profile",
    tip: "Edit your name, currency, budget and password; delete your account",
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col h-screen sticky top-0 bg-white dark:bg-[#0d1829] border-r border-slate-200 dark:border-[#1e3352] transition-all duration-200 z-30",
        collapsed ? "w-14" : "w-56"
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-between h-14 px-3 border-b border-slate-200 dark:border-[#1e3352] shrink-0">
        {!collapsed && (
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">F</div>
            <span className="font-semibold text-sm text-slate-900 dark:text-slate-100">FinRAG AI</span>
          </Link>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto p-1.5 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {NAV.map(({ href, icon: Icon, label, tip }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <div key={href} className="relative group">
              <Link
                href={href}
                className={cn(
                  "flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors duration-150",
                  active
                    ? "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-200"
                )}
              >
                <Icon className={cn("w-4 h-4 shrink-0", active ? "text-blue-600 dark:text-blue-400" : "")} />
                {!collapsed && <span className="truncate">{label}</span>}
              </Link>
              {/* Hover tooltip */}
              <div className={cn(
                "absolute left-full ml-2 top-1/2 -translate-y-1/2 z-50",
                "px-2.5 py-1.5 rounded-lg shadow-card-lg text-xs text-white bg-slate-800 dark:bg-slate-900 max-w-52",
                "opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 whitespace-normal leading-snug",
                collapsed ? "block" : "hidden"
              )}>
                <span className="font-medium">{label}</span>
                <br />
                <span className="text-slate-300">{tip}</span>
              </div>
              {/* Tooltip for expanded: show on icon hover */}
              {!collapsed && (
                <div className={cn(
                  "absolute left-full ml-2 top-1/2 -translate-y-1/2 z-50",
                  "px-2.5 py-1.5 rounded-lg shadow-card-lg text-xs text-white bg-slate-800 dark:bg-slate-900 max-w-64",
                  "opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-200 whitespace-normal leading-snug"
                )}>
                  {tip}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* User */}
      <div className="border-t border-slate-200 dark:border-[#1e3352] p-2 shrink-0">
        {user && !collapsed && (
          <div className="px-2 py-1.5 mb-1">
            <p className="text-xs font-medium text-slate-800 dark:text-slate-200 truncate">{user.name}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 truncate">{user.email}</p>
          </div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg text-sm text-slate-500 dark:text-slate-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 transition-colors"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          {!collapsed && <span>Sign out</span>}
        </button>
      </div>
    </aside>
  );
}
